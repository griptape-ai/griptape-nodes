from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadFailureUnalteredWorkflow,
    ResultPayloadSuccessAlteredWorkflow,
    ResultPayloadSuccessUnalteredWorkflow,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    libraries: list[str]


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    node_types: list[str]


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryRequest(RequestPayload):
    library: str
    node_type: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileRequest(RequestPayload):
    file_path: str
    load_as_default_library: bool = False


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class ListCategoriesInLibraryResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    categories: list[dict]


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


# "Jumbo" event for getting all things say, a GUI might want w/r/t a Library.
@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    library_metadata_details: GetLibraryMetadataResultSuccess
    category_details: ListCategoriesInLibraryResultSuccess
    node_type_name_to_node_metadata_details: dict[str, GetNodeMetadataFromLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


# The "Jumbo-est" of them all. Grabs all info for all libraries in one fell swoop.
@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    library_name_to_library_info: dict[str, GetAllInfoForLibraryResultSuccess]


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryRequest(RequestPayload):
    library_name: str


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultSuccess(ResultPayloadSuccessAlteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class UnloadLibraryFromRegistryResultFailure(ResultPayloadFailure):
    pass
