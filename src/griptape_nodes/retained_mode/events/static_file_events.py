from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
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
        file_url: File URI (file://) for the absolute path where the file will be accessible after upload
    """

    url: str
    headers: dict = field(default_factory=dict)
    method: str = "PUT"
    file_url: str = ""


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
    """Create a presigned URL for downloading a static file from the staticfiles directory via HTTP GET.

    Use when: Providing secure file access to files in the staticfiles directory,
    implementing file sharing, enabling temporary download links, controlling file access permissions.

    Args:
        file_name: Name of the file to be downloaded from the staticfiles directory

    Results: CreateStaticFileDownloadUrlResultSuccess (with URL) | CreateStaticFileDownloadUrlResultFailure (URL creation error)
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlFromPathRequest(RequestPayload):
    """Create a presigned URL for downloading a file from an arbitrary path.

    Use when: Need to create download URLs for files outside the staticfiles directory,
    working with absolute paths, file:// URLs, or workspace-relative paths.

    Args:
        file_path: File path or URL. Accepts:
                   - file:// URLs (e.g., "file:///absolute/path/to/file.jpg")
                   - Absolute paths (e.g., "/absolute/path/to/file.jpg")
                   - Workspace-relative paths (e.g., "relative/path/to/file.jpg")

    Results: CreateStaticFileDownloadUrlResultSuccess (with URL) | CreateStaticFileDownloadUrlResultFailure (URL creation error)
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Static file download URL created successfully.

    Args:
        url: Presigned URL for downloading the file
        file_url: File URI (file://) for the absolute path to the file that was used to create the download URL
    """

    url: str
    file_url: str = ""


@dataclass
@PayloadRegistry.register
class CreateStaticFileDownloadUrlResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Static file download URL creation failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str


@dataclass
@PayloadRegistry.register
class LoadBytesFromLocationRequest(RequestPayload):
    """Load bytes from a location string.

    Supports three location types:
    - HTTP/HTTPS URLs: https://example.com/image.png
    - File paths: /path/to/file.png or file:///path/to/file.png
    - Data URIs: data:image/png;base64,iVBORw0K...

    Use when: Node needs to load content from a location string into memory as bytes
    for processing, validation, or transformation.

    Results: LoadBytesFromLocationResultSuccess (with content bytes) |
             LoadBytesFromLocationResultFailure (download error, invalid format, timeout)

    Args:
        location: Location string - URL, file path, or data URI
        timeout: Download timeout in seconds (default: 120)
    """

    location: str
    timeout: float = 120.0


@dataclass
@PayloadRegistry.register
class LoadBytesFromLocationResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successfully loaded bytes from location.

    Args:
        content: Raw bytes loaded from location (omitted from websocket for size)
    """

    content: bytes = field(metadata={"omit_from_serialization": True})


@dataclass
@PayloadRegistry.register
class LoadBytesFromLocationResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to load bytes from location.

    Common failure scenarios:
    - Cannot load from empty/None location
    - Invalid location string
    - Download timeout
    - HTTP error (404, 403, etc.)
    - Invalid base64 encoding in data URI
    - File not found
    """

    # result_details inherited from ResultPayloadFailure


@dataclass
@PayloadRegistry.register
class LoadBase64DataUriFromLocationRequest(RequestPayload):
    """Load from location and convert to base64 data URI for API submission.

    Most common pattern for generation APIs requiring inline base64 images.
    Returns format: "data:image/png;base64,iVBORw0K..."

    Handles same input types as LoadArtifactBytesRequest.

    Use when: Submitting images/media to external APIs (OpenAI, Anthropic, etc.) that
    require base64 data URIs. Automatically handles downloading from URLs and encoding.

    Results: LoadBase64DataUriFromLocationResultSuccess (with data URI string) |
             LoadBase64DataUriFromLocationResultFailure (download error, encoding error, timeout)

    Args:
        artifact_or_url: Mixed input - artifact, URL, path, or encoded data
        timeout: Download timeout in seconds (default: 120)
        media_type: MIME type for data URI (default: "image/png")
    """

    artifact_or_url: Any
    timeout: float = 120.0
    media_type: str = "image/png"


@dataclass
@PayloadRegistry.register
class LoadBase64DataUriFromLocationResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successfully loaded from location as base64 data URI.

    Args:
        data_uri: Base64 data URI string (e.g., "data:image/png;base64,iVBORw0K...") (omitted from websocket for size)
    """

    data_uri: str = field(metadata={"omit_from_serialization": True})


@dataclass
@PayloadRegistry.register
class LoadBase64DataUriFromLocationResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to load from location as base64 data URI.

    Common failure scenarios:
    - Cannot load None artifact
    - Cannot extract value from artifact
    - Download failed
    - Invalid data format
    - Encoding error
    """

    # result_details inherited from ResultPayloadFailure


@dataclass
@PayloadRegistry.register
class LoadAndSaveFromLocationRequest(RequestPayload):
    """Load bytes from location and save to static storage.

    Supports three location types:
    - HTTP/HTTPS URLs: https://example.com/image.png
    - File paths: /path/to/file.png or file:///path/to/file.png
    - Data URIs: data:image/png;base64,iVBORw0K...

    Common pattern: Download generated media from provider, save to local/cloud storage.
    Uses use_direct_save=True internally to return stable storage paths.

    Use when: Node receives media location from external API and needs to save it to
    workspace storage. Typical in generation nodes (image/video/audio) that download
    results from provider APIs.

    Results: LoadAndSaveFromLocationResultSuccess (with artifact/path) |
             LoadAndSaveFromLocationResultFailure (download error, save error, timeout)

    Args:
        location: Location string - URL, file path, or data URI
        filename: Filename to save as (e.g., "video_123.mp4")
        timeout: Download timeout in seconds (default: 120)
        artifact_type: Artifact class to return (VideoUrlArtifact, ImageUrlArtifact, etc.)
                      If None, returns the saved path string.
        existing_file_policy: How to handle existing files (default: OVERWRITE)
    """

    location: str
    filename: str
    timeout: float = 120.0
    artifact_type: type | None = None
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE


@dataclass
@PayloadRegistry.register
class LoadAndSaveFromLocationResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successfully loaded from location and saved media to storage.

    Args:
        artifact: Either an artifact instance (ImageUrlArtifact, VideoUrlArtifact, etc.)
                 if artifact_type was provided, or the saved path string if not.
    """

    artifact: Any


@dataclass
@PayloadRegistry.register
class LoadAndSaveFromLocationResultFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Failed to load from location and save media.

    Common failure scenarios:
    - Failed to load (timeout, HTTP error, network error)
    - Failed to save (disk full, permission error, invalid path)
    """

    # result_details inherited from ResultPayloadFailure
