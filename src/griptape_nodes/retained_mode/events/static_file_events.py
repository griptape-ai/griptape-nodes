from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateStaticFileRequest(RequestPayload):
    """Request to create a static file.

    Args:
        content: Content of the file base64 encoded
        file_name: Name of the file to create
    """

    content: str
    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    url: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error: str
