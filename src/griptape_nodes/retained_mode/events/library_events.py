from dataclasses import dataclass

from griptape_nodes.node_library.library_registry import LibraryMetadata, NodeMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


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
