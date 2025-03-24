from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResult_Success(ResultPayload_Success):
    libraries: list[str]


@dataclass
@PayloadRegistry.register
class ListRegisteredLibrariesResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResult_Success(ResultPayload_Success):
    node_types: list[str]


@dataclass
@PayloadRegistry.register
class ListNodeTypesInLibraryResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryRequest(RequestPayload):
    library: str
    node_type: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResult_Success(ResultPayload_Success):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataFromLibraryResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileRequest(RequestPayload):
    file_path: str
    load_as_default_library: bool = False


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResult_Success(ResultPayload_Success):
    library_name: str


@dataclass
@PayloadRegistry.register
class RegisterLibraryFromFileResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResult_Success(ResultPayload_Success):
    categories: list[dict]


@dataclass
@PayloadRegistry.register
class ListCategoriesInLibraryResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResult_Success(ResultPayload_Success):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetLibraryMetadataResult_Failure(ResultPayload_Failure):
    pass


# "Jumbo" event for getting all things say, a GUI might want w/r/t a Library.
@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryRequest(RequestPayload):
    library: str


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResult_Success(ResultPayload_Success):
    library_metadata_details: GetLibraryMetadataResult_Success
    category_details: ListCategoriesInLibraryResult_Success
    node_type_name_to_node_metadata_details: dict[str, GetNodeMetadataFromLibraryResult_Success]


@dataclass
@PayloadRegistry.register
class GetAllInfoForLibraryResult_Failure(ResultPayload_Failure):
    pass


# The "Jumbo-est" of them all. Grabs all info for all libraries in one fell swoop.
@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResult_Success(ResultPayload_Success):
    library_name_to_library_info: dict[str, GetAllInfoForLibraryResult_Success]


@dataclass
@PayloadRegistry.register
class GetAllInfoForAllLibrariesResult_Failure(ResultPayload_Failure):
    pass
