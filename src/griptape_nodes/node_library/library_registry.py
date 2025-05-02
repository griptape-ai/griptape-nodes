from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, Self, cast

from griptape.mixins.singleton_mixin import SingletonMixin

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class LibraryNameAndVersion(NamedTuple):
    library_name: str
    library_version: str


class LibraryRegistry(SingletonMixin):
    """Singleton registry to manage many libraries."""

    _libraries: dict[str, Library]

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
            msg = f"Library '{name}' already registered."
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
    def register_node_type_from_library(cls, library: Library, node_class_name: str) -> str | None:
        """Register a node type from a library. Returns an error string for forensics."""
        # Does a node class of this name already exist?
        library_collisions = LibraryRegistry.get_libraries_with_node_type(node_class_name)
        if library_collisions:
            if library.name in library_collisions:
                details = f"Attempted to register Node class '{node_class_name}' from Library '{library.name}', but a Node with that name from that Library was already registered. Check to ensure you aren't re-adding the same libraries multiple times."
                logger.error(details)
                return details

            details = f"When registering Node class '{node_class_name}', Nodes with the same class name were already registered from the following Libraries: '{library_collisions}'. This is a collision. If you want to use this Node, you will need to specify the Library name in addition to the Node class name so that it can be disambiguated."
            logger.warning(details)
            return details

        return None

    @classmethod
    def get_libraries_with_node_type(cls, node_type: str) -> list[str]:
        instance = cls()
        libraries = []
        for library_name, library in instance._libraries.items():
            if library.has_node_type(node_type):
                libraries.append(library_name)
        return libraries

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
            # Find its library.
            libraries_with_node_type = LibraryRegistry.get_libraries_with_node_type(node_type)
            if len(libraries_with_node_type) == 1:
                specific_library_name = libraries_with_node_type[0]
                dest_library = instance.get_library(specific_library_name)
            elif len(libraries_with_node_type) > 1:
                msg = f"Attempted to create a node of type '{node_type}' with no library name specified. The following libraries have nodes in them with the same name: {libraries_with_node_type}. In order to disambiguate, specify the library this node should come from."
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

    def register_new_node_type(self, node_class: type[BaseNode], metadata: dict | None = None) -> str | None:
        """Register a new node type in this library. Returns an error string for forensics, or None if all clear."""
        # We only need to register the name of the node within the library.
        node_class_as_str = node_class.__name__

        # Let the registry know.
        registry_details = LibraryRegistry.register_node_type_from_library(
            library=self, node_class_name=node_class_as_str
        )

        self._node_types[node_class_as_str] = node_class
        if metadata is None:
            self._node_metadata[node_class_as_str] = {}
        else:
            self._node_metadata[node_class_as_str] = metadata
        return registry_details

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

    def has_node_type(self, node_type: str) -> bool:
        return node_type in self._node_types

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
