from pydantic.dataclasses import dataclass

from griptape_nodes.node_library.library_registry import LibraryMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class ListRegisteredLibrariesRequest(RequestPayload):
    pass


@PayloadRegistry.register
class ListRegisteredLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    libraries: list[str]


@PayloadRegistry.register
class ListRegisteredLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class ListNodeTypesInLibraryRequest(RequestPayload):
    library: str


@PayloadRegistry.register
class ListNodeTypesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    node_types: list[str]


@PayloadRegistry.register
class ListNodeTypesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetNodeMetadataFromLibraryRequest(RequestPayload):
    library: str
    node_type: str


@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: NodeMetadata


@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RegisterLibraryFromFileRequest(RequestPayload):
    file_path: str
    load_as_default_library: bool = False


@PayloadRegistry.register
class RegisterLibraryFromFileResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    library_name: str


@PayloadRegistry.register
class RegisterLibraryFromFileResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierRequest(RequestPayload):
    requirement_specifier: str
    library_config_name: str = "griptape_nodes_library.json"


@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    library_name: str


@PayloadRegistry.register
class RegisterLibraryFromRequirementSpecifierResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class ListCategoriesInLibraryRequest(RequestPayload):
    library: str


@PayloadRegistry.register
class ListCategoriesInLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    categories: list[dict]


@PayloadRegistry.register
class ListCategoriesInLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetLibraryMetadataRequest(RequestPayload):
    library: str


@PayloadRegistry.register
class GetLibraryMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: LibraryMetadata


@PayloadRegistry.register
class GetLibraryMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# "Jumbo" event for getting all things say, a GUI might want w/r/t a Library.
@PayloadRegistry.register
class GetAllInfoForLibraryRequest(RequestPayload):
    library: str


@PayloadRegistry.register
class GetAllInfoForLibraryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    library_metadata_details: GetLibraryMetadataResultSuccess
    category_details: ListCategoriesInLibraryResultSuccess
    node_type_name_to_node_metadata_details: dict[str, GetNodeMetadataFromLibraryResultSuccess]


@PayloadRegistry.register
class GetAllInfoForLibraryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# The "Jumbo-est" of them all. Grabs all info for all libraries in one fell swoop.
@PayloadRegistry.register
class GetAllInfoForAllLibrariesRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    library_name_to_library_info: dict[str, GetAllInfoForLibraryResultSuccess]


@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class UnloadLibraryFromRegistryRequest(RequestPayload):
    library_name: str


@PayloadRegistry.register
class UnloadLibraryFromRegistryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class UnloadLibraryFromRegistryResultFailure(ResultPayloadFailure):
    pass
