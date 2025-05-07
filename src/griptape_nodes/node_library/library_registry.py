from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, Self, cast

from griptape.mixins.singleton_mixin import SingletonMixin
from pydantic import BaseModel

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class LibraryNameAndVersion(NamedTuple):
    library_name: str
    library_version: str


class Dependencies(BaseModel):
    """Dependencies for the library.

    This can include other libraries, as well as external packages that need to
    be installed with pip.
    """

    pip_dependencies: list[str] | None = None
    pip_install_flags: list[str] | None = None


class LibraryMetadata(BaseModel):
    """Metadata that explains details about the library, including versioning and search details."""

    author: str
    description: str
    library_version: str
    engine_version: str
    tags: list[str]
    dependencies: Dependencies | None = None
    # If True, this library will be surfaced to Griptape Nodes customers when listing Node Libraries available to them.
    is_griptape_nodes_searchable: bool = True


class NodeMetadata(BaseModel):
    """Metadata about each node within the library, which informs where in the hierarchy it sits, details on usage, and tags to assist search."""

    category: str
    description: str
    display_name: str
    tags: list[str] | None = None


class CategoryDefinition(BaseModel):
    """Defines categories within a library, which influences how nodes are organized within an editor."""

    title: str
    description: str
    color: str
    icon: str


class NodeDefinition(BaseModel):
    """Defines a node within a library, including class name and file name and metadata about the node."""

    class_name: str
    file_path: str
    metadata: NodeMetadata


class Setting(BaseModel):
    """Defines a library-specific setting, which will automatically be injected into the user's Configuration."""

    category: str  # Name of the category in the config
    contents: dict[str, Any]  # The actual settings content
    description: str | None = None  # Optional description for the setting


class LibrarySchema(BaseModel):
    """Schema for a library definition file.

    The schema that defines the structure of a Griptape Nodes library,
    including the nodes and workflows it contains, as well as metadata about the
    library itself.
    """

    name: str
    library_schema_version: str
    metadata: LibraryMetadata
    categories: list[dict[str, CategoryDefinition]]
    nodes: list[NodeDefinition]
    workflows: list[str] | None = None
    scripts: list[str] | None = None
    settings: list[Setting] | None = None
    is_default_library: bool | None = None


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
        library_data: LibrarySchema,
        *,
        mark_as_default_library: bool = False,
    ) -> Library:
        instance = cls()

        if library_data.name in instance._libraries:
            msg = f"Library '{library_data.name}' already registered."
            raise KeyError(msg)
        library = Library(library_data=library_data, is_default_library=mark_as_default_library)
        instance._libraries[library_data.name] = library
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

        # Put the default libraries first.
        default_libraries = [k for k, v in instance._libraries.items() if v.is_default_library()]
        other_libraries = [k for k, v in instance._libraries.items() if not v.is_default_library()]
        sorted_list = default_libraries + other_libraries
        return sorted_list

    @classmethod
    def register_node_type_from_library(cls, library: Library, node_class_name: str) -> str | None:
        """Register a node type from a library. Returns an error string for forensics."""
        # Does a node class of this name already exist?
        library_collisions = LibraryRegistry.get_libraries_with_node_type(node_class_name)
        if library_collisions:
            library_data = library.get_library_data()
            if library_data.name in library_collisions:
                details = f"Attempted to register Node class '{node_class_name}' from Library '{library_data.name}', but a Node with that name from that Library was already registered. Check to ensure you aren't re-adding the same libraries multiple times."
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

    _library_data: LibrarySchema
    _is_default_library: bool
    # Maintain fast lookups for node class name to class and to its metadata.
    _node_types: dict[str, type[BaseNode]]
    _node_metadata: dict[str, NodeMetadata]

    def __init__(
        self,
        library_data: LibrarySchema,
        *,
        is_default_library: bool = False,
    ) -> None:
        self._library_data = library_data

        # If they didn't make it explicit, allow an override.
        if self._library_data.is_default_library is None:
            self._library_data.is_default_library = is_default_library

        self._is_default_library = self._library_data.is_default_library

        self._node_types = {}
        self._node_metadata = {}

    def register_new_node_type(self, node_class: type[BaseNode], metadata: NodeMetadata) -> str | None:
        """Register a new node type in this library. Returns an error string for forensics, or None if all clear."""
        # We only need to register the name of the node within the library.
        node_class_as_str = node_class.__name__

        # Let the registry know.
        registry_details = LibraryRegistry.register_node_type_from_library(
            library=self, node_class_name=node_class_as_str
        )

        self._node_types[node_class_as_str] = node_class
        self._node_metadata[node_class_as_str] = metadata
        return registry_details

    def get_library_data(self) -> LibrarySchema:
        return self._library_data

    def create_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> BaseNode:
        """Create a new node instance of the specified type."""
        node_class = self._node_types.get(node_type)
        if not node_class:
            raise KeyError(self._library_data.name, node_type)
        # Inject the metadata ABOUT the node from the Library
        # into the node's metadata blob.
        if metadata is None:
            metadata = {}
        library_node_metadata = self._node_metadata.get(node_type, {})
        metadata["library_node_metadata"] = library_node_metadata
        metadata["library"] = self._library_data.name
        metadata["node_type"] = node_type
        node = node_class(name=name, metadata=metadata)
        return node

    def get_registered_nodes(self) -> list[str]:
        """Get a list of all registered node types."""
        return list(self._node_types.keys())

    def has_node_type(self, node_type: str) -> bool:
        return node_type in self._node_types

    def get_node_metadata(self, node_type: str) -> NodeMetadata:
        if node_type not in self._node_metadata:
            raise KeyError(self._library_data.name, node_type)
        return self._node_metadata[node_type]

    def get_categories(self) -> list[dict[str, CategoryDefinition]]:
        return self._library_data.categories

    def is_default_library(self) -> bool:
        return self._is_default_library

    def get_metadata(self) -> LibraryMetadata:
        return self._library_data.metadata
