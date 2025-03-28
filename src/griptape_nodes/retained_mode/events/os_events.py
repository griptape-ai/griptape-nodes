from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileRequest(RequestPayload):
    path_to_file: str


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultFailure(ResultPayloadFailure):
    pass
