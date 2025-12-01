import base64
import hashlib
import logging
import mimetypes
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from griptape_nodes.retained_mode.events.file_download_events import (
    CancelFileDownloadRequest,
    CancelFileDownloadResultFailure,
    CancelFileDownloadResultSuccess,
    CompleteFileDownloadEvent,
    FileChunkDownloadResponse,
    RequestNextChunkRequest,
    RequestNextChunkResultFailure,
    StartWebSocketFileDownloadRequest,
    StartWebSocketFileDownloadResultFailure,
    StartWebSocketFileDownloadResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

logger = logging.getLogger("griptape_nodes")

# Default chunk size: 64KB
DEFAULT_CHUNK_SIZE = 64 * 1024

# Default session timeout: 5 minutes
DEFAULT_SESSION_TIMEOUT = 5 * 60


@dataclass
class DownloadSession:
    """Represents an active file download session."""

    session_id: str
    file_path: str
    file_url: str
    file_size: int
    total_chunks: int
    chunk_size: int
    content_type: str | None
    file_data: bytes
    chunks_sent: int
    created_at: float
    last_activity: float


class FileDownloadManager:
    """Manages WebSocket-based file downloads with chunking support."""

    def __init__(
        self,
        config_manager: ConfigManager,
        static_files_manager: StaticFilesManager,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize the FileDownloadManager.

        Args:
            config_manager: The ConfigManager instance for accessing configuration.
            static_files_manager: The StaticFilesManager instance for file operations.
            event_manager: The EventManager instance for event handling.
        """
        self.config_manager = config_manager
        self.static_files_manager = static_files_manager

        # Active download sessions
        self._active_downloads: dict[str, DownloadSession] = {}
        self._downloads_lock = threading.RLock()

        # Configuration
        self.chunk_size = DEFAULT_CHUNK_SIZE
        self.session_timeout = DEFAULT_SESSION_TIMEOUT

        # Register event handlers
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                StartWebSocketFileDownloadRequest, self.on_start_websocket_file_download_request
            )
            event_manager.assign_manager_to_request_type(RequestNextChunkRequest, self.on_request_next_chunk_request)
            event_manager.assign_manager_to_request_type(
                CancelFileDownloadRequest, self.on_cancel_file_download_request
            )

    def on_start_websocket_file_download_request(
        self,
        request: StartWebSocketFileDownloadRequest,
    ) -> StartWebSocketFileDownloadResultSuccess | StartWebSocketFileDownloadResultFailure:
        """Handle start WebSocket file download request."""
        # Validate request parameters (similar to static files manager)
        if request.file_name is None and request.file_path is None:
            return StartWebSocketFileDownloadResultFailure(
                error="Either file_name or file_path must be provided", result_details="No file identifier specified"
            )

        if request.file_name is not None and request.file_path is not None:
            return StartWebSocketFileDownloadResultFailure(
                error="Only one of file_name or file_path should be provided",
                result_details="Ambiguous file identifier",
            )

        try:
            # Determine file path to load
            if request.file_name is not None:
                # Legacy file_name parameter - use workflow-aware directory resolution
                resolved_directory = self.static_files_manager._get_static_files_directory()
                file_path = self.config_manager.workspace_path / Path(resolved_directory) / request.file_name
            else:
                # Use file_path parameter
                file_path = Path(request.file_path)

                # Resolve relative paths
                if not file_path.is_absolute():
                    workspace_dir = Path(self.config_manager.get_config_value("workspace_directory"))
                    file_path = workspace_dir / file_path

            # Check if file exists and is readable
            if not file_path.exists():
                return StartWebSocketFileDownloadResultFailure(
                    error=f"File not found: {file_path}", result_details="Requested file does not exist"
                )

            if not file_path.is_file():
                return StartWebSocketFileDownloadResultFailure(
                    error=f"Path is not a file: {file_path}", result_details="Requested path is not a regular file"
                )

            # Load file data
            file_data = file_path.read_bytes()
            file_size = len(file_data)

            # Calculate total chunks needed
            total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size if file_size > 0 else 1

            # Determine content type
            content_type, _ = mimetypes.guess_type(str(file_path))

            # Generate unique session ID
            session_id = str(uuid.uuid4())

            # Construct full file:// URL
            file_url = f"file://{file_path.resolve()}"

            # Create download session
            current_time = time.time()
            session = DownloadSession(
                session_id=session_id,
                file_path=str(file_path),
                file_url=file_url,
                file_size=file_size,
                total_chunks=total_chunks,
                chunk_size=self.chunk_size,
                content_type=content_type,
                file_data=file_data,
                chunks_sent=0,
                created_at=current_time,
                last_activity=current_time,
            )

            with self._downloads_lock:
                # Clean up expired sessions before adding new one
                self._cleanup_expired_sessions()
                self._active_downloads[session_id] = session

            logger.info(
                "Started WebSocket file download session %s for %s (%s bytes, %s chunks)",
                session_id,
                file_url,
                file_size,
                total_chunks,
            )

            return StartWebSocketFileDownloadResultSuccess(
                session_id=session_id,
                total_size=file_size,
                total_chunks=total_chunks,
                file_url=file_url,
                content_type=content_type,
                chunk_size=self.chunk_size,
                result_details=f"Download session started for {file_url}",
            )

        except Exception as e:
            logger.error("Failed to start WebSocket file download: %s", e)
            return StartWebSocketFileDownloadResultFailure(
                error=f"Failed to start download session: {e}", result_details="Error initializing file download"
            )

    def on_request_next_chunk_request(
        self,
        request: RequestNextChunkRequest,
    ) -> FileChunkDownloadResponse | RequestNextChunkResultFailure:
        """Handle request for next chunk in download."""
        with self._downloads_lock:
            session = self._active_downloads.get(request.session_id)
            if not session:
                return RequestNextChunkResultFailure(
                    session_id=request.session_id,
                    error="Download session not found or expired",
                    result_details=f"Session {request.session_id} is not active",
                )

        # Validate expected chunk index
        if request.expected_chunk_index != session.chunks_sent:
            return RequestNextChunkResultFailure(
                session_id=request.session_id,
                error=f"Chunk index mismatch: expected {session.chunks_sent}, got {request.expected_chunk_index}",
                result_details="Client and server are out of sync",
            )

        # Check if all chunks have been sent
        if session.chunks_sent >= session.total_chunks:
            # Send completion event
            completion_event = CompleteFileDownloadEvent(
                session_id=request.session_id,
                total_bytes_sent=session.file_size,
                total_chunks_sent=session.chunks_sent,
                file_url=session.file_url,
                result_details=f"Download completed for {session.file_url}",
            )

            # Cleanup session
            self._cleanup_session(request.session_id)

            return completion_event

        try:
            # Get chunk data
            chunk_index = session.chunks_sent
            start_offset = chunk_index * self.chunk_size
            end_offset = min(start_offset + self.chunk_size, session.file_size)
            chunk_data = session.file_data[start_offset:end_offset]

            # Encode chunk as base64
            chunk_data_b64 = base64.b64encode(chunk_data).decode("utf-8")

            # Calculate checksum
            chunk_checksum = hashlib.md5(chunk_data).hexdigest()

            # Check if this is the final chunk
            is_final_chunk = chunk_index == session.total_chunks - 1

            # Update session
            with self._downloads_lock:
                session.chunks_sent += 1
                session.last_activity = time.time()

            logger.debug(
                "Sending chunk %s/%s for session %s (%s bytes)",
                chunk_index,
                session.total_chunks - 1,
                request.session_id,
                len(chunk_data),
            )

            return FileChunkDownloadResponse(
                session_id=request.session_id,
                chunk_index=chunk_index,
                chunk_data=chunk_data_b64,
                chunk_checksum=chunk_checksum,
                is_final_chunk=is_final_chunk,
                result_details=f"Chunk {chunk_index} ready for download",
            )

        except Exception as e:
            logger.error("Failed to prepare chunk %s for session %s: %s", session.chunks_sent, request.session_id, e)
            return RequestNextChunkResultFailure(
                session_id=request.session_id,
                error=f"Failed to prepare chunk: {e}",
                result_details="Error reading chunk data",
            )

    def on_cancel_file_download_request(
        self,
        request: CancelFileDownloadRequest,
    ) -> CancelFileDownloadResultSuccess | CancelFileDownloadResultFailure:
        """Handle cancel file download request."""
        with self._downloads_lock:
            session = self._active_downloads.get(request.session_id)
            if not session:
                return CancelFileDownloadResultFailure(
                    session_id=request.session_id,
                    error="Download session not found or already completed",
                    result_details=f"Session {request.session_id} is not active",
                )

            chunks_sent = session.chunks_sent

        try:
            # Cleanup session
            self._cleanup_session(request.session_id)

            reason_msg = f" (reason: {request.reason})" if request.reason else ""
            logger.info("Cancelled WebSocket file download session %s%s", request.session_id, reason_msg)

            return CancelFileDownloadResultSuccess(
                session_id=request.session_id,
                chunks_sent=chunks_sent,
                result_details=f"Download session cancelled{reason_msg}",
            )

        except Exception as e:
            logger.error("Failed to cancel download session %s: %s", request.session_id, e)
            return CancelFileDownloadResultFailure(
                session_id=request.session_id,
                error=f"Failed to cancel session: {e}",
                result_details="Error during session cancellation",
            )

    def _cleanup_session(self, session_id: str) -> None:
        """Clean up a specific download session."""
        with self._downloads_lock:
            session = self._active_downloads.pop(session_id, None)
            if session:
                logger.debug("Cleaned up download session %s for %s", session_id, session.file_url)

    def _cleanup_expired_sessions(self) -> None:
        """Clean up expired download sessions."""
        current_time = time.time()
        expired_sessions = []

        for session_id, session in self._active_downloads.items():
            if (current_time - session.last_activity) > self.session_timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info("Cleaning up expired download session %s", session_id)
            self._cleanup_session(session_id)
