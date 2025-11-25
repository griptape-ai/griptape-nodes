"""WebRTC data channel messages for peer-to-peer image transfer.

Note: Field names use camelCase (fileId, fileName, etc.) to maintain compatibility
with the frontend WebRTC protocol. This intentionally violates Python naming conventions.
"""
# ruff: noqa: N815

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Message type literals for pattern matching
MessageType = Literal[
    "image_upload_start",
    "image_chunk",
    "image_upload_complete",
    "image_download_request",
    "upload_success",
    "upload_error",
    "image_download_start",
    "image_download_chunk",
    "image_download_complete",
    "image_download_error",
]


# Base message classes
@dataclass
class WebRTCDataChannelMessage:
    """Base class for all WebRTC data channel messages."""


# Upload Messages (Frontend → Backend)
@dataclass
class ImageUploadStartMessage(WebRTCDataChannelMessage):
    """Initiates an image upload via WebRTC data channel.

    Sent first to indicate the beginning of an image upload with metadata.
    Backend should create upload session and prepare to receive chunks.

    Args:
        type: Always "image_upload_start"
        fileId: Unique identifier for this upload (format: image_{timestamp}_{random})
        fileName: Original filename from the user
        fileType: MIME type of the image (must start with "image/")
        totalBytes: Total file size in bytes
        totalChunks: Number of chunks that will be sent
    """

    type: Literal["image_upload_start"]
    fileId: str
    fileName: str
    fileType: str
    totalBytes: int
    totalChunks: int


@dataclass
class ImageChunkMessage(WebRTCDataChannelMessage):
    """Sends a chunk of image data during upload.

    Sent for each 16KB chunk of the image file. Data is Base64 encoded for JSON transmission.

    Args:
        type: Always "image_chunk"
        fileId: Same ID from the upload start message
        chunkIndex: Zero-based index of this chunk (0 to totalChunks-1)
        totalChunks: Total number of chunks (same as in start message)
        data: Base64 encoded binary data for this chunk (16KB max per chunk)
    """

    type: Literal["image_chunk"]
    fileId: str
    chunkIndex: int
    totalChunks: int
    data: str  # Base64 encoded chunk data


@dataclass
class ImageUploadCompleteMessage(WebRTCDataChannelMessage):
    """Signals completion of image upload.

    Sent after all chunks have been transmitted. Backend should assemble file and respond.

    Args:
        type: Always "image_upload_complete"
        fileId: Same ID from previous messages
    """

    type: Literal["image_upload_complete"]
    fileId: str


# Download Messages (Frontend → Backend)
@dataclass
class ImageDownloadRequestMessage(WebRTCDataChannelMessage):
    """Requests download of an image via WebRTC data channel.

    Frontend sends this to request a previously uploaded or generated image.

    Args:
        type: Always "image_download_request"
        fileId: Unique identifier of the image to download (UUID part)
        fileName: Original filename of the image
        requestId: Unique identifier for this download request (format: download_req_{timestamp}_{random})
    """

    type: Literal["image_download_request"]
    fileId: str
    fileName: str
    requestId: str


# Upload Response Messages (Backend → Frontend)
@dataclass
class UploadSuccessMessage(WebRTCDataChannelMessage):
    """Upload completed successfully with generated URL.

    Backend sends this after successful file assembly and storage.

    Args:
        type: Always "upload_success"
        fileId: Same file ID from upload messages
        url: WebRTC upload URL (format: webrtc://uploaded/{fileId}/{fileName})
    """

    type: Literal["upload_success"]
    fileId: str
    url: str


@dataclass
class UploadErrorMessage(WebRTCDataChannelMessage):
    """Upload failed with error details.

    Backend sends this when upload processing fails.

    Args:
        type: Always "upload_error"
        fileId: File ID from upload messages (if available)
        error: Human-readable error description
    """

    type: Literal["upload_error"]
    fileId: str | None
    error: str


# Download Response Messages (Backend → Frontend)
@dataclass
class ImageDownloadStartMessage(WebRTCDataChannelMessage):
    """Begins download transmission with file metadata.

    Backend sends this in response to download request before sending chunks.

    Args:
        type: Always "image_download_start"
        fileId: Same file ID from the request
        requestId: Same request ID from the request
        fileName: Original filename of the image
        fileType: MIME type of the image
        totalBytes: Total file size in bytes
        totalChunks: Number of chunks that will be sent
    """

    type: Literal["image_download_start"]
    fileId: str
    requestId: str
    fileName: str
    fileType: str
    totalBytes: int
    totalChunks: int


@dataclass
class ImageDownloadChunkMessage(WebRTCDataChannelMessage):
    """Sends a chunk of image data during download.

    Backend sends this for each 16KB chunk of the requested image.

    Args:
        type: Always "image_download_chunk"
        fileId: Same file ID from previous messages
        requestId: Same request ID from previous messages
        chunkIndex: Zero-based index of this chunk (0 to totalChunks-1)
        totalChunks: Total number of chunks (same as in start message)
        data: Base64 encoded binary data for this chunk (16KB max per chunk)
    """

    type: Literal["image_download_chunk"]
    fileId: str
    requestId: str
    chunkIndex: int
    totalChunks: int
    data: str  # Base64 encoded chunk data


@dataclass
class ImageDownloadCompleteMessage(WebRTCDataChannelMessage):
    """Signals completion of image download.

    Backend sends this after all chunks have been transmitted successfully.

    Args:
        type: Always "image_download_complete"
        fileId: Same file ID from previous messages
        requestId: Same request ID from previous messages
    """

    type: Literal["image_download_complete"]
    fileId: str
    requestId: str


@dataclass
class ImageDownloadErrorMessage(WebRTCDataChannelMessage):
    """Download failed with error details.

    Backend sends this when download processing fails.

    Args:
        type: Always "image_download_error"
        fileId: Same file ID from previous messages
        requestId: Same request ID from previous messages
        error: Human-readable error description
    """

    type: Literal["image_download_error"]
    fileId: str
    requestId: str
    error: str


# Type unions for message handling
UploadMessage = ImageUploadStartMessage | ImageChunkMessage | ImageUploadCompleteMessage
DownloadRequestMessage = ImageDownloadRequestMessage
UploadResponseMessage = UploadSuccessMessage | UploadErrorMessage
DownloadResponseMessage = (
    ImageDownloadStartMessage | ImageDownloadChunkMessage | ImageDownloadCompleteMessage | ImageDownloadErrorMessage
)

# All possible data channel messages
WebRTCMessage = UploadMessage | DownloadRequestMessage | UploadResponseMessage | DownloadResponseMessage


# ruff: noqa: PLR0911, C901
def parse_message(message_json: str) -> WebRTCMessage:
    """Parse JSON message string into structured WebRTC message object.

    Args:
        message_json: JSON string received from data channel

    Returns:
        Parsed message object with proper type

    Raises:
        ValueError: If message format is invalid
        KeyError: If required fields are missing
    """
    import json

    try:
        data = json.loads(message_json)
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON: {e}"
        raise ValueError(msg) from e

    message_type = data.get("type")

    # Upload messages
    if message_type == "image_upload_start":
        return ImageUploadStartMessage(**data)
    if message_type == "image_chunk":
        return ImageChunkMessage(**data)
    if message_type == "image_upload_complete":
        return ImageUploadCompleteMessage(**data)

    # Download request
    if message_type == "image_download_request":
        return ImageDownloadRequestMessage(**data)

    # Upload responses
    if message_type == "upload_success":
        return UploadSuccessMessage(**data)
    if message_type == "upload_error":
        return UploadErrorMessage(**data)

    # Download responses
    if message_type == "image_download_start":
        return ImageDownloadStartMessage(**data)
    if message_type == "image_download_chunk":
        return ImageDownloadChunkMessage(**data)
    if message_type == "image_download_complete":
        return ImageDownloadCompleteMessage(**data)
    if message_type == "image_download_error":
        return ImageDownloadErrorMessage(**data)

    msg = f"Unknown message type: {message_type}"
    raise ValueError(msg)


def serialize_message(message: WebRTCMessage) -> str:
    """Serialize structured message object to JSON string.

    Args:
        message: Structured WebRTC message object

    Returns:
        JSON string ready for data channel transmission
    """
    import json
    from dataclasses import asdict

    return json.dumps(asdict(message))
