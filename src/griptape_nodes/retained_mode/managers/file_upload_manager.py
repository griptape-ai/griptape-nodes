import base64
import hashlib
import logging
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from griptape_nodes.retained_mode.events.file_upload_events import (
    CancelFileUploadRequest,
    CancelFileUploadResultFailure,
    CancelFileUploadResultSuccess,
    CompleteFileUploadRequest,
    CompleteFileUploadResultFailure,
    CompleteFileUploadResultSuccess,
    FileChunkUploadRequest,
    FileChunkUploadResultFailure,
    FileChunkUploadResultSuccess,
    StartWebSocketFileUploadRequest,
    StartWebSocketFileUploadResultFailure,
    StartWebSocketFileUploadResultSuccess,
)
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

logger = logging.getLogger("griptape_nodes")

# Default chunk size: 64KB
DEFAULT_CHUNK_SIZE = 64 * 1024

# Default session timeout: 5 minutes
DEFAULT_SESSION_TIMEOUT = 5 * 60

# Maximum number of missing chunks to show in error messages
MAX_MISSING_CHUNKS_TO_DISPLAY = 10


@dataclass
class UploadSession:
    """Represents an active file upload session."""

    session_id: str
    file_name: str
    file_size: int
    total_chunks: int
    chunk_size: int
    content_type: str | None
    temp_file_path: str
    chunks_received: dict[int, bytes]  # chunk_index -> chunk_data
    created_at: float
    last_activity: float


class FileUploadManager:
    """Manages WebSocket-based file uploads with chunking support."""

    def __init__(
        self,
        config_manager: ConfigManager,
        static_files_manager: StaticFilesManager,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize the FileUploadManager.

        Args:
            config_manager: The ConfigManager instance for accessing configuration.
            static_files_manager: The StaticFilesManager instance for file operations.
            event_manager: The EventManager instance for event handling.
        """
        self.config_manager = config_manager
        self.static_files_manager = static_files_manager

        # Active upload sessions
        self._active_uploads: dict[str, UploadSession] = {}
        self._uploads_lock = threading.RLock()

        # Configuration
        self.chunk_size = DEFAULT_CHUNK_SIZE
        self.session_timeout = DEFAULT_SESSION_TIMEOUT

        # Register event handlers
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                StartWebSocketFileUploadRequest, self.on_start_websocket_file_upload_request
            )
            event_manager.assign_manager_to_request_type(FileChunkUploadRequest, self.on_file_chunk_upload_request)
            event_manager.assign_manager_to_request_type(
                CompleteFileUploadRequest, self.on_complete_file_upload_request
            )
            event_manager.assign_manager_to_request_type(CancelFileUploadRequest, self.on_cancel_file_upload_request)

    def on_start_websocket_file_upload_request(
        self,
        request: StartWebSocketFileUploadRequest,
    ) -> StartWebSocketFileUploadResultSuccess | StartWebSocketFileUploadResultFailure:
        """Handle start WebSocket file upload request."""
        if request.file_size <= 0:
            return StartWebSocketFileUploadResultFailure(
                error="File size must be greater than 0", result_details="Invalid file size provided"
            )

        if not request.file_name:
            return StartWebSocketFileUploadResultFailure(
                error="File name cannot be empty", result_details="File name is required for upload"
            )

        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())

            # Calculate total chunks needed
            total_chunks = (request.file_size + self.chunk_size - 1) // self.chunk_size

            # Create temporary file for assembling chunks
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{request.file_name}") as temp_file:
                temp_file_path = temp_file.name

            # Generate file path (similar to static files)
            workspace_dir = Path(self.config_manager.get_config_value("workspace_directory"))
            static_files_dir = workspace_dir / self.config_manager.get_config_value(
                "static_files_directory", default="staticfiles"
            )
            file_path = str(static_files_dir / request.file_name)

            # Create upload session
            current_time = time.time()
            session = UploadSession(
                session_id=session_id,
                file_name=request.file_name,
                file_size=request.file_size,
                total_chunks=total_chunks,
                chunk_size=self.chunk_size,
                content_type=request.content_type,
                temp_file_path=temp_file_path,
                chunks_received={},
                created_at=current_time,
                last_activity=current_time,
            )

            with self._uploads_lock:
                # Clean up expired sessions before adding new one
                self._cleanup_expired_sessions()
                self._active_uploads[session_id] = session

            logger.info(
                "Started WebSocket file upload session %s for %s (%s bytes, %s chunks)",
                session_id,
                request.file_name,
                request.file_size,
                total_chunks,
            )

            return StartWebSocketFileUploadResultSuccess(
                session_id=session_id,
                total_chunks=total_chunks,
                file_path=file_path,
                chunk_size=self.chunk_size,
                result_details=f"Upload session started for {request.file_name}",
            )

        except Exception as e:
            logger.error("Failed to start WebSocket file upload for %s: %s", request.file_name, e)
            return StartWebSocketFileUploadResultFailure(
                error=f"Failed to start upload session: {e}",
                result_details=f"Error initializing upload for {request.file_name}",
            )

    def _validate_chunk_request(
        self, request: FileChunkUploadRequest, session: UploadSession
    ) -> FileChunkUploadResultFailure | None:
        """Validate chunk upload request. Returns error result if validation fails, None if valid."""
        # Validate chunk index
        if request.chunk_index < 0 or request.chunk_index >= session.total_chunks:
            return FileChunkUploadResultFailure(
                session_id=request.session_id,
                chunk_index=request.chunk_index,
                error=f"Invalid chunk index {request.chunk_index}, expected 0-{session.total_chunks - 1}",
                result_details="Chunk index out of range",
            )
        return None

    def on_file_chunk_upload_request(
        self,
        request: FileChunkUploadRequest,
    ) -> FileChunkUploadResultSuccess | FileChunkUploadResultFailure:
        """Handle file chunk upload request."""
        with self._uploads_lock:
            session = self._active_uploads.get(request.session_id)
            if not session:
                return FileChunkUploadResultFailure(
                    session_id=request.session_id,
                    chunk_index=request.chunk_index,
                    error="Upload session not found or expired",
                    result_details=f"Session {request.session_id} is not active",
                )

        # Validate chunk request
        validation_error = self._validate_chunk_request(request, session)
        if validation_error:
            return validation_error

        # Check if chunk already received
        if request.chunk_index in session.chunks_received:
            logger.warning("Duplicate chunk %s for session %s", request.chunk_index, request.session_id)
            return FileChunkUploadResultSuccess(
                session_id=request.session_id,
                chunk_index=request.chunk_index,
                bytes_received=len(session.chunks_received[request.chunk_index]),
                result_details="Chunk already received (duplicate)",
            )

        try:
            # Decode base64 chunk data
            chunk_data = base64.b64decode(request.chunk_data)

            # Validate chunk size (except for last chunk)
            expected_size = self.chunk_size
            if request.chunk_index == session.total_chunks - 1:
                # Last chunk can be smaller
                remaining_bytes = session.file_size - (request.chunk_index * self.chunk_size)
                expected_size = remaining_bytes

            if len(chunk_data) != expected_size:
                return FileChunkUploadResultFailure(
                    session_id=request.session_id,
                    chunk_index=request.chunk_index,
                    error=f"Chunk size mismatch: expected {expected_size}, got {len(chunk_data)}",
                    result_details="Invalid chunk size",
                )

            # Validate checksum if provided
            if request.chunk_checksum:
                actual_checksum = hashlib.md5(chunk_data).hexdigest()
                if actual_checksum != request.chunk_checksum:
                    return FileChunkUploadResultFailure(
                        session_id=request.session_id,
                        chunk_index=request.chunk_index,
                        error="Chunk checksum validation failed",
                        result_details=f"Expected {request.chunk_checksum}, got {actual_checksum}",
                    )

            # Store chunk data
            with self._uploads_lock:
                session.chunks_received[request.chunk_index] = chunk_data
                session.last_activity = time.time()

            logger.debug(
                "Received chunk %s/%s for session %s", request.chunk_index, session.total_chunks - 1, request.session_id
            )

            return FileChunkUploadResultSuccess(
                session_id=request.session_id,
                chunk_index=request.chunk_index,
                bytes_received=len(chunk_data),
                result_details=f"Chunk {request.chunk_index} received successfully",
            )

        except Exception as e:
            logger.error("Failed to process chunk %s for session %s: %s", request.chunk_index, request.session_id, e)
            return FileChunkUploadResultFailure(
                session_id=request.session_id,
                chunk_index=request.chunk_index,
                error=f"Failed to process chunk: {e}",
                result_details="Error processing chunk data",
            )

    def on_complete_file_upload_request(
        self,
        request: CompleteFileUploadRequest,
    ) -> CompleteFileUploadResultSuccess | CompleteFileUploadResultFailure:
        """Handle complete file upload request."""
        with self._uploads_lock:
            session = self._active_uploads.get(request.session_id)
            if not session:
                return CompleteFileUploadResultFailure(
                    session_id=request.session_id,
                    error="Upload session not found or expired",
                    result_details=f"Session {request.session_id} is not active",
                )

        # Verify all chunks received
        if len(session.chunks_received) != session.total_chunks:
            missing_chunks = set(range(session.total_chunks)) - set(session.chunks_received.keys())
            return CompleteFileUploadResultFailure(
                session_id=request.session_id,
                error=f"Missing {len(missing_chunks)} chunks: {sorted(missing_chunks)[:MAX_MISSING_CHUNKS_TO_DISPLAY]}{'...' if len(missing_chunks) > MAX_MISSING_CHUNKS_TO_DISPLAY else ''}",
                result_details=f"Expected {session.total_chunks} chunks, received {len(session.chunks_received)}",
            )

        # Verify total chunks sent matches
        if request.total_chunks_sent != session.total_chunks:
            return CompleteFileUploadResultFailure(
                session_id=request.session_id,
                error=f"Chunk count mismatch: expected {session.total_chunks}, client reported {request.total_chunks_sent}",
                result_details="Client and server chunk counts don't match",
            )

        try:
            # Assemble file from chunks
            with Path(session.temp_file_path).open("wb") as f:
                total_bytes = 0
                for chunk_index in range(session.total_chunks):
                    chunk_data = session.chunks_received[chunk_index]
                    f.write(chunk_data)
                    total_bytes += len(chunk_data)

            # Verify total file size
            if total_bytes != session.file_size:
                return CompleteFileUploadResultFailure(
                    session_id=request.session_id,
                    error=f"File size mismatch: expected {session.file_size}, got {total_bytes}",
                    result_details="Assembled file size doesn't match expected size",
                )

            # Save file using StaticFilesManager
            with Path(session.temp_file_path).open("rb") as f:
                file_content = f.read()

            file_url = self.static_files_manager.save_static_file(file_content, session.file_name)

            # Cleanup
            self._cleanup_session(request.session_id)

            logger.info(
                "Completed WebSocket file upload for %s (%s bytes) -> %s", session.file_name, total_bytes, file_url
            )

            return CompleteFileUploadResultSuccess(
                session_id=request.session_id,
                file_path=session.file_name,
                file_url=file_url,
                total_bytes=total_bytes,
                result_details=f"File upload completed: {file_url}",
            )

        except Exception as e:
            logger.error("Failed to complete file upload for session %s: %s", request.session_id, e)
            # Don't cleanup session on failure - allow retry
            return CompleteFileUploadResultFailure(
                session_id=request.session_id,
                error=f"Failed to complete upload: {e}",
                result_details="Error finalizing uploaded file",
            )

    def on_cancel_file_upload_request(
        self,
        request: CancelFileUploadRequest,
    ) -> CancelFileUploadResultSuccess | CancelFileUploadResultFailure:
        """Handle cancel file upload request."""
        with self._uploads_lock:
            session = self._active_uploads.get(request.session_id)
            if not session:
                return CancelFileUploadResultFailure(
                    session_id=request.session_id,
                    error="Upload session not found or already completed",
                    result_details=f"Session {request.session_id} is not active",
                )

            chunks_processed = len(session.chunks_received)

        try:
            # Cleanup session
            self._cleanup_session(request.session_id)

            reason_msg = f" (reason: {request.reason})" if request.reason else ""
            logger.info("Cancelled WebSocket file upload session %s%s", request.session_id, reason_msg)

            return CancelFileUploadResultSuccess(
                session_id=request.session_id,
                chunks_processed=chunks_processed,
                result_details=f"Upload session cancelled{reason_msg}",
            )

        except Exception as e:
            logger.error("Failed to cancel upload session %s: %s", request.session_id, e)
            return CancelFileUploadResultFailure(
                session_id=request.session_id,
                error=f"Failed to cancel session: {e}",
                result_details="Error during session cancellation",
            )

    def _cleanup_session(self, session_id: str) -> None:
        """Clean up a specific upload session."""
        with self._uploads_lock:
            session = self._active_uploads.pop(session_id, None)
            if session:
                # Remove temporary file
                try:
                    temp_path = Path(session.temp_file_path)
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception as e:
                    logger.warning("Failed to remove temporary file %s: %s", session.temp_file_path, e)

    def _cleanup_expired_sessions(self) -> None:
        """Clean up expired upload sessions."""
        current_time = time.time()
        expired_sessions = []

        for session_id, session in self._active_uploads.items():
            if (current_time - session.last_activity) > self.session_timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            logger.info("Cleaning up expired upload session %s", session_id)
            self._cleanup_session(session_id)
