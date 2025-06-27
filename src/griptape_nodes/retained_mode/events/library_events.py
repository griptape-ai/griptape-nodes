from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibraryMetadata, LibrarySchema, NodeMetadata
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    libraries: list[str]


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    node_types: list[str]


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryRequest(RequestPayload):
    library: str
    node_type: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: NodeMetadata


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileRequest(RequestPayload):
    """Request to load library metadata from a JSON file without loading node modules.

    This provides a lightweight way to get library schema information without the overhead
    of dynamically importing Python modules. Useful for metadata queries, validation,
    and library discovery operations.

    Args:
        file_path: Absolute path to the library JSON schema file to load.
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result from loading library metadata.

    Contains the validated library schema that can be used for metadata queries,
    node type discovery, and other operations that don't require the actual
    node classes to be loaded.

    Args:
        library_schema: The validated LibrarySchema object containing all metadata
                       about the library including nodes, categories, and settings.
        file_path: The file path from which the library metadata was loaded.
    """

    library_schema: LibrarySchema
    file_path: str


@dataclass
@PayloadRegistry.register
class LoadLibraryMetadataFromFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result from loading library metadata with detailed error information.

    Provides comprehensive error details including the specific failure type and
    a list of problems encountered during loading. This allows callers to understand
    exactly what went wrong and take appropriate action.

    Args:
        library_path: Path to the library file that failed to load.
        library_name: Name of the library if it could be extracted from the JSON,
                     None if the name couldn't be determined.
        status: The LibraryStatus enum indicating the type of failure
               (MISSING, UNUSABLE, etc.).
        problems: List of specific error messages describing what went wrong
                 during loading (JSON parse errors, validation failures, etc.).
    """

    library_path: str
    library_name: str | None
    status: LibraryManager.LibraryStatus
    problems: list[str]


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesRequest(RequestPayload):
    """Request to load metadata for all libraries from configuration without loading node modules.

    This loads metadata from both:
    1. Library JSON files specified in configuration
    2. Sandbox library (dynamically generated from Python files)

    Provides a lightweight way to discover all available libraries and their schemas
    without the overhead of importing Python modules or registering them in the system.
    """


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result from loading metadata for all libraries.

    Contains metadata for all discoverable libraries from both configuration files
    and sandbox directory, with clear separation between successful loads and failures.

    Args:
        successful_libraries: List of successful library metadata loading results,
                             including both config-based libraries and sandbox library if applicable.
        failed_libraries: List of detailed failure results for libraries that couldn't be loaded,
                         including both config-based libraries and sandbox library if applicable.
    """

    successful_libraries: list[LoadLibraryMetadataFromFileResultSuccess]
    failed_libraries: list[LoadLibraryMetadataFromFileResultFailure]


@dataclass
@PayloadRegistry.register
class LoadMetadataForAllLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result from loading metadata for all libraries.

    This indicates a systemic failure (e.g., configuration access issues)
    rather than individual library loading failures, which are captured
    in the success result's failed_libraries list.
    """


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileRequest(RequestPayload):
    file_path: str
    load_as_default_library: bool = False


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    library_name: str


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierRequest(RequestPayload):
    requirement_specifier: str
    library_config_name: str = "griptape_nodes_library.json"


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    library_name: str


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    categories: list[dict]


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: LibraryMetadata


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# "Jumbo" event for getting all things say, a GUI might want w/r/t a Library.
@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    library_metadata_details: GetLibraryMetadataResultSuccess
    category_details: ListCategoriesInLibraryResultSuccess
    node_type_name_to_node_metadata_details: dict[str, GetNodeMetadataFromLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# The "Jumbo-est" of them all. Grabs all info for all libraries in one fell swoop.
@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    library_name_to_library_info: dict[str, GetAllInfoForLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryRequest(RequestPayload):
    library_name: str


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesRequest(RequestPayload):
    """WARNING: This request will CLEAR ALL CURRENT WORKFLOW STATE!

    Reloading all libraries requires clearing all existing workflows, nodes, and execution state
    because there is no way to comprehensively erase references to old Python modules.
    All current work will be lost and must be recreated after the reload operation completes.

    Use this operation only when you need to pick up changes to library code during development
    or when library corruption requires a complete reset.
    """


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ReloadAllLibrariesResultFailure(ResultPayloadFailure):
    pass
