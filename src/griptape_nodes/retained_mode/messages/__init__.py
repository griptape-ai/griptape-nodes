"""WebRTC message types for data channel communication."""

from .webrtc_messages import (
    DownloadRequestMessage,
    DownloadResponseMessage,
    ImageChunkMessage,
    ImageDownloadChunkMessage,
    ImageDownloadCompleteMessage,
    ImageDownloadErrorMessage,
    # Download request (Frontend → Backend)
    ImageDownloadRequestMessage,
    # Download responses (Backend → Frontend)
    ImageDownloadStartMessage,
    ImageUploadCompleteMessage,
    # Upload messages (Frontend → Backend)
    ImageUploadStartMessage,
    MessageType,
    UploadErrorMessage,
    # Type unions
    UploadMessage,
    UploadResponseMessage,
    # Upload responses (Backend → Frontend)
    UploadSuccessMessage,
    # Base types
    WebRTCDataChannelMessage,
    WebRTCMessage,
    # Utility functions
    parse_message,
    serialize_message,
)

__all__ = [
    "DownloadRequestMessage",
    "DownloadResponseMessage",
    "ImageChunkMessage",
    "ImageDownloadChunkMessage",
    "ImageDownloadCompleteMessage",
    "ImageDownloadErrorMessage",
    "ImageDownloadRequestMessage",
    "ImageDownloadStartMessage",
    "ImageUploadCompleteMessage",
    "ImageUploadStartMessage",
    "MessageType",
    "UploadErrorMessage",
    "UploadMessage",
    "UploadResponseMessage",
    "UploadSuccessMessage",
    "WebRTCDataChannelMessage",
    "WebRTCMessage",
    "parse_message",
    "serialize_message",
]
