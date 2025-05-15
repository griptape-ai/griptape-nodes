from pydantic.dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class OpenAssociatedFileRequest(RequestPayload):
    path_to_file: str


@PayloadRegistry.register
class OpenAssociatedFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class OpenAssociatedFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
