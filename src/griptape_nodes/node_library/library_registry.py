from __future__ import annotations

import logging
from typing import Any, NamedTuple, Self, cast

from griptape.mixins.singleton_mixin import SingletonMixin

from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class LibraryNodeIdentifier(NamedTuple):
    """Unique identifier for a node type."""

    library: str
    node_name: str


class LibraryRegistry(SingletonMixin):
    """Singleton registry to manage many libraries."""

    _libraries: dict[str, Library]

    # Keep a list of Node names to the Library it belongs to.
    # This means the user doesn't have to specify the library as long as there are no collisions.
    # Names that collide are NOT included in the aliases list, but rather a separate table.
    _node_aliases: dict[str, str]

    # If there are collisions between node names between libraries, store them here.
    # These will need to be specified using explicit library + node name.
    _collision_node_names_to_library_names: dict[str, set[str]]

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._libraries = {}
            cls._node_aliases = {}
            cls._collision_node_names_to_library_names = {}
        return cast("Self", cls._instance)

    @classmethod
    def generate_new_library(
        cls,
        name: str,
        mark_as_default_library: bool = False,  # noqa: FBT001, FBT002
        categories: list[dict] | None = None,
    ) -> Library:
        instance = cls()

        if name in instance._libraries:
            msg = f"Library type '{name}' already registered."
            raise KeyError(msg)
        library = Library(name=name, is_default_library=mark_as_default_library, categories=categories)
        instance._libraries[name] = library
        return library

    @classmethod
    def unregister_library(cls, library_name: str) -> None:
        instance = cls()

        if library_name not in instance._libraries:
            msg = f"Library '{library_name}' was requested to be unregistered, but it wasn't registered in the first place."
            raise KeyError(msg)

        # See which nodes in the collision table were attached to this library.
        # A previous collision may get "promoted" back to being an alias when this library goes away.
        collisions_to_delete = []  # Track separately so we can delete after the iter loop.
        for collision_node_name, library_name_set in instance._collision_node_names_to_library_names.items():
            if library_name in library_name_set:
                # Remove it, then see if we've "un-collisioned" this name.
                library_name_set.remove(library_name)
                if len(library_name_set) == 1:
                    # No longer a collision. Promote back to the alias table and mark this collision for delete.
                    lone_library = library_name_set.pop()
                    instance._node_aliases[collision_node_name] = lone_library
                    collisions_to_delete.append(collision_node_name)

        # Actually delete any collisions outside of the iteration loop.
        for collision_to_delete in collisions_to_delete:
            del instance._collision_node_names_to_library_names[collision_to_delete]

        # Now walk the alias table and delete anything that matches this library.
        aliases_to_delete = []
        for alias_node_name, alias_library_name in instance._node_aliases.items():
            if alias_library_name == library_name:
                aliases_to_delete.append(alias_node_name)

        # Actually delete the aliases.
        for alias_node_to_delete in aliases_to_delete:
            del instance._node_aliases[alias_node_to_delete]

        # Now delete the library from the registry.
        del instance._libraries[library_name]

    @classmethod
    def get_library(cls, name: str) -> Library:
        instance = cls()
        if name not in instance._libraries:
            msg = f"Library '{name}' not found"
            raise KeyError(msg)
        return instance._libraries[name]

    @classmethod
    def list_libraries(cls) -> list[str]:
        instance = cls()
        return list(instance._libraries.keys())

    @classmethod
    def register_node_type_from_library(cls, library: Library, node_class_name: str) -> None:
        instance = cls()
        # Does a node class of this name already have a collision established?
        if node_class_name in instance._collision_node_names_to_library_names:
            collision_set = instance._collision_node_names_to_library_names[node_class_name]
            # Make sure we're not re-adding the same node/library combo.
            if library.name in collision_set:
                logger.info(
                    "Attempted to register Node class '%s' from Library '%s', but a Node with that name from that Library was already registered. Check to ensure you aren't re-adding the same libraries multiple times.",
                    node_class_name,
                    library.name,
                )
                return

            # Append it to the set.
            logger.info(
                "When registering Node class '%s', Nodes with the same class name were already registered from the following Libraries: %s, you will need to specify the Library name in addition to the Node class name so that it can be disambiguated.",
                node_class_name,
                collision_set,
            )
            collision_set.add(library.name)
            return

        # See if there's a collision with the aliases.
        if node_class_name in instance._node_aliases:
            collision_library_name = instance._node_aliases[node_class_name]
            # Make sure we're not trying to register the same node/library combo.
            if library.name == collision_library_name:
                logger.info(
                    "Attempted to register Node class '%s' from Library '%s', but a Node with that name from that Library was already registered. Check to ensure you aren't re-adding the same libraries multiple times.",
                    node_class_name,
                    library.name,
                )
                return
            # OK, legit collision. Move from the aliases table to the collision table.
            logger.warning(
                "Attempted to register a Node class '%s' from Library '%s', but a Node of that class name already existed from Library '%s'. In order to create these types of node, you will need to specify the Library name in addition to the Node class name so that it can be disambiguated.",
                node_class_name,
                library.name,
                collision_library_name,
            )

            collision_set = set()
            collision_set.add(collision_library_name)
            collision_set.add(library.name)

            # Add to the collision table.
            instance._collision_node_names_to_library_names[node_class_name] = collision_set

            # Remove from the aliases table.
            del instance._node_aliases[node_class_name]
            return

        # Hunky-dory to add it as an alias.
        instance._node_aliases[node_class_name] = library.name

    @classmethod
    def create_node(
        cls,
        node_type: str,
        name: str,
        metadata: dict[Any, Any] | None = None,
        specific_library_name: str | None = None,
    ) -> BaseNode:
        instance = cls()
        if specific_library_name is None:
            # Does this node class exist in our aliases table?
            if node_type in instance._node_aliases:
                dest_library_name = instance._node_aliases[node_type]
                dest_library = instance.get_library(dest_library_name)
            # Maybe it is a collision?
            elif node_type in instance._collision_node_names_to_library_names:
                collision_set = instance._collision_node_names_to_library_names[node_type]
                msg = f"Attempted to create a node of type '{node_type}', with no library name specified. The following libraries have nodes in them with the same name: {collision_set}. In order to disambiguate, specify the library this node should come from."
                raise KeyError(msg)
            else:
                msg = f"No node type '{node_type}' could be found in any of the libraries registered."
                raise KeyError(msg)
        else:
            # See if the library exists.
            dest_library = instance.get_library(specific_library_name)

        # Ask the library to create the node.
        return dest_library.create_node(node_type=node_type, name=name, metadata=metadata)


class Library:
    """A collection of nodes curated by library author.

    Handles registration and creation of nodes.
    """

    name: str
    _metadata: dict | None
    _node_types: dict[str, type[BaseNode]]
    _node_metadata: dict[str, dict]
    _categories: list[dict] | None
    _is_default_library: bool

    def __init__(
        self,
        name: str,
        metadata: dict | None = None,
        categories: list[dict] | None = None,
        is_default_library: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self.name = name
        if metadata is None:
            self._metadata = {}
        else:
            self._metadata = metadata
        self._node_types = {}
        self._node_metadata = {}
        if categories is None:
            self._categories = []
        else:
            self._categories = categories
        self._is_default_library = is_default_library
        self._metadata["is_default_library"] = self._is_default_library

    def register_new_node_type(self, node_class: type[BaseNode], metadata: dict | None = None) -> None:
        """Register a new node type in this library."""
        if not issubclass(node_class, BaseNode):
            msg = f"{node_class.__name__} must inherit from BaseNode"
            raise TypeError(msg)
        # We only need to register the name of the node within the library.
        node_class_as_str = node_class.__name__
        self._node_types[node_class_as_str] = node_class
        if metadata is None:
            self._node_metadata[node_class_as_str] = {}
        else:
            self._node_metadata[node_class_as_str] = metadata

        # Let the registry know.
        LibraryRegistry.register_node_type_from_library(library=self, node_class_name=node_class_as_str)

    def create_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> BaseNode:
        """Create a new node instance of the specified type."""
        node_class = self._node_types.get(node_type)
        if not node_class:
            raise KeyError(self.name, node_type)
        # Inject the metadata ABOUT the node from the Library
        # into the node's metadata blob.
        if metadata is None:
            metadata = {}
        library_node_metadata = self._node_metadata.get(node_type, {})
        metadata["library_node_metadata"] = library_node_metadata
        metadata["library"] = self.name
        metadata["node_type"] = node_type
        node = node_class(name=name, metadata=metadata)
        return node

    def get_registered_nodes(self) -> list[str]:
        """Get a list of all registered node types."""
        return list(self._node_types.keys())

    def get_node_metadata(self, node_type: str) -> dict:
        if node_type not in self._node_metadata:
            raise KeyError(self.name, node_type)
        return self._node_metadata[node_type]

    def get_categories(self) -> list[dict]:
        if self._categories is None:
            return []
        return self._categories

    def is_default_library(self) -> bool:
        return self._is_default_library

    def get_metadata(self) -> dict:
        if self._metadata is None:
            return {}
        return self._metadata
