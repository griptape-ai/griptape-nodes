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
class StartWebSocketFileDownloadRequest(RequestPayload):
    """Start a WebSocket-based file download with chunking support.

    Use when: Static file server is unavailable, downloading large files via WebSocket,
    implementing fallback file transfer mechanism, enabling chunked file downloads.

    Results: StartWebSocketFileDownloadResultSuccess (with session info) | StartWebSocketFileDownloadResultFailure (download init error)

    Args:
        file_name: Name of the file to be downloaded (deprecated, use file_path)
        file_path: Path to the file (absolute or workspace-relative). If relative,
                   resolved relative to workspace root. If outside workspace, file
                   will be copied to staticfiles directory.

    Note: Exactly one of file_name or file_path must be provided.
    """

    file_name: str | None = None
    file_path: str | None = None


@dataclass
@PayloadRegistry.register
class StartWebSocketFileDownloadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """WebSocket file download started successfully.

    Args:
        session_id: Unique identifier for this download session
        total_size: Total size of the file in bytes
        total_chunks: Total number of chunks that will be sent
        file_name: Name of the file being downloaded
        content_type: MIME type of the file (if available)
        chunk_size: Size of each chunk in bytes (except possibly the last one)
    """

    session_id: str
    total_size: int
    total_chunks: int
    file_name: str
    chunk_size: int
    content_type: str | None = None


@dataclass
@PayloadRegistry.register
class StartWebSocketFileDownloadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """WebSocket file download start failed.

    Args:
        error: Detailed error message describing the failure
    """

    error: str


@dataclass
@PayloadRegistry.register
class FileChunkDownloadResponse(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """A single chunk of file data sent from server to client.

    Use when: Server is sending file data in chunks, streaming large files,
    implementing progressive download, handling WebSocket file transfer.

    Args:
        session_id: Download session identifier
        chunk_index: Zero-based index of this chunk in the file
        chunk_data: Base64-encoded chunk data
        chunk_checksum: Optional checksum for chunk validation
        is_final_chunk: True if this is the last chunk of the file
    """

    session_id: str
    chunk_index: int
    chunk_data: str = field(metadata={"omit_from_result": True})
    chunk_checksum: str | None = None
    is_final_chunk: bool = False


@dataclass
@PayloadRegistry.register
class RequestNextChunkRequest(RequestPayload):
    """Request the next chunk in a WebSocket file download.

    Use when: Client is ready to receive the next chunk, implementing flow control,
    handling client-paced downloads, acknowledging chunk receipt.

    Results: FileChunkDownloadResponse (next chunk) | RequestNextChunkResultFailure (request failed)

    Args:
        session_id: Download session identifier
        expected_chunk_index: The index of the chunk the client expects to receive next
    """

    session_id: str
    expected_chunk_index: int


@dataclass
@PayloadRegistry.register
class RequestNextChunkResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Next chunk request failed.

    Args:
        session_id: Download session identifier
        error: Detailed error message describing the failure
    """

    session_id: str
    error: str


@dataclass
@PayloadRegistry.register
class CompleteFileDownloadEvent(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File download completed successfully.

    Use when: All chunks have been sent to client, finalizing download session,
    triggering post-download processing, completing download workflow.

    Args:
        session_id: Download session identifier
        total_bytes_sent: Total number of bytes that were sent
        total_chunks_sent: Total number of chunks that were sent
        file_name: Name of the downloaded file
    """

    session_id: str
    total_bytes_sent: int
    total_chunks_sent: int
    file_name: str


@dataclass
@PayloadRegistry.register
class CancelFileDownloadRequest(RequestPayload):
    """Cancel an active WebSocket file download session.

    Use when: User cancels download, handling download errors, cleaning up failed downloads,
    implementing timeout handling, freeing server resources.

    Results: CancelFileDownloadResultSuccess (download cancelled) | CancelFileDownloadResultFailure (cancellation failed)

    Args:
        session_id: Download session identifier to cancel
        reason: Optional reason for cancellation
    """

    session_id: str
    reason: str | None = None


@dataclass
@PayloadRegistry.register
class CancelFileDownloadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File download cancelled successfully.

    Args:
        session_id: Download session identifier that was cancelled
        chunks_sent: Number of chunks that were sent before cancellation
    """

    session_id: str
    chunks_sent: int


@dataclass
@PayloadRegistry.register
class CancelFileDownloadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File download cancellation failed.

    Args:
        session_id: Download session identifier
        error: Detailed error message describing the failure
    """

    session_id: str
    error: str
