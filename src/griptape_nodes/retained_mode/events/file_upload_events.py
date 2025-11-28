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
class StartWebSocketFileUploadRequest(RequestPayload):
    """Start a WebSocket-based file upload with chunking support.

    Use when: Static file server is unavailable, uploading large files via WebSocket,
    implementing fallback file transfer mechanism, enabling chunked file uploads.

    Results: StartWebSocketFileUploadResultSuccess (with session info) | StartWebSocketFileUploadResultFailure (upload init error)

    Args:
        file_name: Name of the file to be uploaded
        file_size: Total size of the file in bytes
        content_type: MIME type of the file (optional)
    """

    file_name: str
    file_size: int
    content_type: str | None = None


@dataclass
@PayloadRegistry.register
class StartWebSocketFileUploadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """WebSocket file upload started successfully.

    Args:
        session_id: Unique identifier for this upload session
        total_chunks: Total number of chunks expected for this upload
        file_path: Server-side path where the file will be stored
        chunk_size: Size of each chunk in bytes (except possibly the last one)
    """

    session_id: str
    total_chunks: int
    file_path: str
    chunk_size: int


@dataclass
@PayloadRegistry.register
class StartWebSocketFileUploadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """WebSocket file upload start failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str


@dataclass
@PayloadRegistry.register
class FileChunkUploadRequest(RequestPayload):
    """Upload a single chunk of a file via WebSocket.

    Use when: Sending file data in chunks, resuming interrupted uploads,
    implementing progressive file transfer, handling large file uploads.

    Results: FileChunkUploadResultSuccess (chunk accepted) | FileChunkUploadResultFailure (chunk rejected)

    Args:
        session_id: Upload session identifier
        chunk_index: Zero-based index of this chunk in the file
        chunk_data: Base64-encoded chunk data
        chunk_checksum: Optional checksum for chunk validation
    """

    session_id: str
    chunk_index: int
    chunk_data: str = field(metadata={"omit_from_result": True})
    chunk_checksum: str | None = None


@dataclass
@PayloadRegistry.register
class FileChunkUploadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File chunk uploaded successfully.

    Args:
        session_id: Upload session identifier
        chunk_index: Index of the chunk that was processed
        bytes_received: Number of bytes received for this chunk
    """

    session_id: str
    chunk_index: int
    bytes_received: int


@dataclass
@PayloadRegistry.register
class FileChunkUploadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File chunk upload failed.

    Args:
        session_id: Upload session identifier
        chunk_index: Index of the chunk that failed
        error: Detailed error message describing the failure
    """

    session_id: str
    chunk_index: int
    error: str


@dataclass
@PayloadRegistry.register
class CompleteFileUploadRequest(RequestPayload):
    """Complete a WebSocket file upload and finalize the file.

    Use when: All chunks have been uploaded, finalizing file assembly,
    triggering post-upload processing, completing upload workflow.

    Results: CompleteFileUploadResultSuccess (upload completed) | CompleteFileUploadResultFailure (completion failed)

    Args:
        session_id: Upload session identifier
        total_chunks_sent: Total number of chunks that were sent (for verification)
    """

    session_id: str
    total_chunks_sent: int


@dataclass
@PayloadRegistry.register
class CompleteFileUploadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File upload completed successfully.

    Args:
        session_id: Upload session identifier
        file_path: Final server-side path of the uploaded file
        file_url: URL where the uploaded file can be accessed
        total_bytes: Total number of bytes in the completed file
    """

    session_id: str
    file_path: str
    file_url: str
    total_bytes: int


@dataclass
@PayloadRegistry.register
class CompleteFileUploadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File upload completion failed.

    Args:
        session_id: Upload session identifier
        error: Detailed error message describing the failure
    """

    session_id: str
    error: str


@dataclass
@PayloadRegistry.register
class CancelFileUploadRequest(RequestPayload):
    """Cancel an active WebSocket file upload session.

    Use when: User cancels upload, handling upload errors, cleaning up failed uploads,
    implementing timeout handling, freeing server resources.

    Results: CancelFileUploadResultSuccess (upload cancelled) | CancelFileUploadResultFailure (cancellation failed)

    Args:
        session_id: Upload session identifier to cancel
        reason: Optional reason for cancellation
    """

    session_id: str
    reason: str | None = None


@dataclass
@PayloadRegistry.register
class CancelFileUploadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File upload cancelled successfully.

    Args:
        session_id: Upload session identifier that was cancelled
        chunks_processed: Number of chunks that were processed before cancellation
    """

    session_id: str
    chunks_processed: int


@dataclass
@PayloadRegistry.register
class CancelFileUploadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File upload cancellation failed.

    Args:
        session_id: Upload session identifier
        error: Detailed error message describing the failure
    """

    session_id: str
    error: str
