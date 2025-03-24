from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileRequest(RequestPayload):
    path_to_file: str


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResult_Failure(ResultPayload_Failure):
    pass
