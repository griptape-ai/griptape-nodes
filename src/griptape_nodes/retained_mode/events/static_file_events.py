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
    """Create a static file from content.

    Use when: Generating files from workflow outputs, creating downloadable content,
    storing processed data, implementing file export functionality.

    Results: CreateStaticFileResultSuccess (with URL) | CreateStaticFileResultFailure (creation error)

    Args:
        content: Content of the file base64 encoded
        file_name: Name of the file to create
    """

    content: str = field(metadata={"omit_from_result": True})
    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Static file created successfully.

    Args:
        url: URL where the static file can be accessed
    """

    url: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Static file creation failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlRequest(RequestPayload):
    """Create a presigned URL for uploading a static file via HTTP PUT.

    Use when: Implementing file upload functionality, allowing direct client uploads,
    enabling large file transfers, implementing drag-and-drop uploads.

    Args:
        file_name: Name of the file to be uploaded

    Results: CreateStaticFileUploadUrlResultSuccess (with URL and headers) | CreateStaticFileUploadUrlResultFailure (URL creation error)
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Static file upload URL created successfully.

    Args:
        url: Presigned URL for uploading the file
        headers: HTTP headers required for the upload request
        method: HTTP method to use for upload (typically PUT)
    """

    url: str
    headers: dict = field(default_factory=dict)
    method: str = "PUT"


@dataclass
@PayloadRegistry.register
class CreateStaticFileUploadUrlResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Static file upload URL creation failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlRequest(RequestPayload):
    """Create a presigned URL for downloading a static file via HTTP GET.

    Use when: Providing secure file access, implementing file sharing,
    enabling temporary download links, controlling file access permissions.

    Args:
        file_name: Name of the file to be downloaded

    Results: CreateStaticFileDownloadUrlResultSuccess (with URL) | CreateStaticFileDownloadUrlResultFailure (URL creation error)
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Static file download URL created successfully.

    Args:
        url: Presigned URL for downloading the file
    """

    url: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Static file download URL creation failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str
