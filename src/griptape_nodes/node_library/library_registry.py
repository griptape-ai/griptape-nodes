from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from pydantic import BaseModel, Field

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.duplicate_node_registration_problem import (
    DuplicateNodeRegistrationProblem,
)
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
    from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

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


class IconVariant(BaseModel):
    """Icon variant for light and dark themes."""

    light: str
    dark: str


class NodeDeprecationMetadata(BaseModel):
    """Metadata about a deprecated node."""

    deprecation_message: str | None = None
    removal_version: str | None = None


class NodeMetadata(BaseModel):
    """Metadata about each node within the library, which informs where in the hierarchy it sits, details on usage, and tags to assist search."""

    category: str
    description: str
    display_name: str
    tags: list[str] | None = None
    icon: str | IconVariant | None = None
    color: str | None = None
    group: str | None = None
    deprecation: NodeDeprecationMetadata | None = None


class CategoryDefinition(BaseModel):
    """Defines categories within a library, which influences how nodes are organized within an editor."""

    title: str
    description: str
    color: str
    icon: str
    group: str | None = None


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
    json_schema: dict[str, Any] | None = Field(
        default=None, alias="schema"
    )  # JSON schema for the setting (including enums)


class LibrarySchema(BaseModel):
    """Schema for a library definition file.

    The schema that defines the structure of a Griptape Nodes library,
    including the nodes and workflows it contains, as well as metadata about the
    library itself.
    """

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.3.0"

    name: str
    library_schema_version: str
    metadata: LibraryMetadata
    categories: list[dict[str, CategoryDefinition]]
    nodes: list[NodeDefinition]
    workflows: list[str] | None = None
    scripts: list[str] | None = None
    settings: list[Setting] | None = None
    is_default_library: bool | None = None
    advanced_library_path: str | None = None


class LibraryRegistry(metaclass=SingletonMeta):
    """Singleton registry to manage many libraries."""

    _libraries: ClassVar[dict[str, Library]] = {}
    _node_aliases: ClassVar[dict[str, Library]] = {}
    _collision_node_names_to_library_names: ClassVar[dict[str, list[str]]] = {}

    @classmethod
    def generate_new_library(
        cls,
        library_data: LibrarySchema,
        *,
        mark_as_default_library: bool = False,
        advanced_library: AdvancedNodeLibrary | None = None,
    ) -> Library:
        instance = cls()

        if library_data.name in instance._libraries:
            msg = f"Library '{library_data.name}' already registered."
            raise KeyError(msg)
        library = Library(
            library_data=library_data, is_default_library=mark_as_default_library, advanced_library=advanced_library
        )
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
    def register_node_type_from_library(cls, library: Library, node_class_name: str) -> LibraryProblem | None:
        """Register a node type from a library. Returns a LibraryProblem if registration fails."""
        # Does a node class of this name already exist?
        library_collisions = LibraryRegistry.get_libraries_with_node_type(node_class_name)
        if library_collisions:
            library_data = library.get_library_data()
            if library_data.name in library_collisions:
                logger.error(
                    "Attempted to register node class '%s' from library '%s', but a node with that name from that library was already registered",
                    node_class_name,
                    library_data.name,
                )
                return DuplicateNodeRegistrationProblem(class_name=node_class_name, library_name=library_data.name)

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
    def get_library_for_node_type(cls, node_type: str, specific_library_name: str | None = None) -> Library:
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

        return dest_library

    @classmethod
    def create_node(
        cls,
        node_type: str,
        name: str,
        metadata: dict[Any, Any] | None = None,
        specific_library_name: str | None = None,
    ) -> BaseNode:
        instance = cls()

        dest_library = instance.get_library_for_node_type(
            node_type=node_type, specific_library_name=specific_library_name
        )

        # Ask the library to create the node.
        return dest_library.create_node(node_type=node_type, name=name, metadata=metadata)

    @classmethod
    def get_all_library_schemas(cls) -> dict[str, dict]:
        """Get schemas from all loaded libraries.

        Returns:
            Dictionary mapping category names to their JSON Schema dicts
        """
        instance = cls()
        schemas = {}

        # Get explicit schemas from loaded libraries
        for library in instance._libraries.values():
            library_data = library.get_library_data()
            if library_data.settings:
                for setting in library_data.settings:
                    if setting.json_schema:
                        schemas[setting.category] = {
                            "type": "object",
                            "properties": setting.json_schema,
                            "title": setting.description or f"{setting.category.title()} Settings",
                        }
                    else:
                        # Create fallback schema for settings without explicit schemas
                        schemas[setting.category] = {
                            "type": "object",
                            "title": setting.description or f"{setting.category.title()} Settings",
                        }

        return schemas


class Library:
    """A collection of nodes curated by library author.

    Handles registration and creation of nodes.
    """

    _library_data: LibrarySchema
    _is_default_library: bool
    # Maintain fast lookups for node class name to class and to its metadata.
    _node_types: dict[str, type[BaseNode]]
    _node_metadata: dict[str, NodeMetadata]
    _advanced_library: AdvancedNodeLibrary | None

    def __init__(
        self,
        library_data: LibrarySchema,
        *,
        is_default_library: bool = False,
        advanced_library: AdvancedNodeLibrary | None = None,
    ) -> None:
        self._library_data = library_data

        # If they didn't make it explicit, allow an override.
        if self._library_data.is_default_library is None:
            self._library_data.is_default_library = is_default_library

        self._is_default_library = self._library_data.is_default_library

        self._node_types = {}
        self._node_metadata = {}
        self._advanced_library = advanced_library

    def register_new_node_type(self, node_class: type[BaseNode], metadata: NodeMetadata) -> LibraryProblem | None:
        """Register a new node type in this library. Returns a LibraryProblem if registration fails, or None if all clear."""
        # We only need to register the name of the node within the library.
        node_class_as_str = node_class.__name__

        # Let the registry know.
        library_problem = LibraryRegistry.register_node_type_from_library(
            library=self, node_class_name=node_class_as_str
        )

        self._node_types[node_class_as_str] = node_class
        self._node_metadata[node_class_as_str] = metadata
        return library_problem

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
            msg = f"Node type '{node_type}' not found in library '{self._library_data.name}'"
            raise KeyError(msg)
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

    def get_advanced_library(self) -> AdvancedNodeLibrary | None:
        """Get the advanced library instance for this library.

        Returns:
            The AdvancedNodeLibrary instance, or None if not set
        """
        return self._advanced_library

    def get_nodes_by_base_type(self, base_type: type) -> list[str]:
        """Get all node types in this library that are subclasses of the specified base type.

        Args:
            base_type: The base class to filter by (e.g., StartNode, ControlNode)

        Returns:
            List of node type names that extend the base type
        """
        matching_nodes = []
        for node_type, node_class in self._node_types.items():
            if issubclass(node_class, base_type):
                matching_nodes.append(node_type)
        return matching_nodes
