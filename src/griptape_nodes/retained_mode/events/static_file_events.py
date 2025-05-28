from dataclasses import dataclass, field

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

    content: str = field(metadata={"omit_from_result": True})
    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    url: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlRequest(RequestPayload):
    """Request to create a presigned URL for uploading a static file via a HTTP PUT.

    Args:
        file_name: Name of the file to be uploaded
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    url: str
    headers: dict = field(default_factory=dict)
    method: str = "PUT"


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlRequest(RequestPayload):
    """Request to create a presigned URL for downloading a static file via a HTTP GET.

    Args:
        file_name: Name of the file to be uploaded
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    url: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error: str
