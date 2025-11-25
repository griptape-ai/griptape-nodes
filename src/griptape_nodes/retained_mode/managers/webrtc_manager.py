"""Manages WebRTC peer-to-peer connections using aiortc."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
import uuid
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from aiortc import RTCConfiguration, RTCDataChannel, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from griptape_nodes.retained_mode.events.webrtc_events import (
    WebRTCConnectRequest,
    WebRTCConnectResultFailure,
    WebRTCConnectResultSuccess,
)
from griptape_nodes.retained_mode.messages.webrtc_messages import (
    ImageChunkMessage,
    ImageDownloadChunkMessage,
    ImageDownloadCompleteMessage,
    ImageDownloadErrorMessage,
    ImageDownloadRequestMessage,
    ImageDownloadStartMessage,
    ImageUploadCompleteMessage,
    ImageUploadStartMessage,
    UploadErrorMessage,
    UploadMessage,
    UploadSuccessMessage,
    parse_message,
    serialize_message,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

logger = logging.getLogger("griptape_nodes")

# Constants for file processing
EXPECTED_PARTS_COUNT = 2
UUID_HEX_LENGTH = 32


class UploadSession:
    """Tracks file upload state for WebRTC file transfers."""

    def __init__(self, file_name: str, file_type: str, total_bytes: int, total_chunks: int) -> None:
        self.file_name = file_name
        self.file_type = file_type
        self.total_bytes = total_bytes
        self.total_chunks = total_chunks
        self.received_chunks: dict[int, bytes] = {}
        self.assembled_data = BytesIO()
        self.is_complete = False


class WebRTCManager:
    """Manages WebRTC peer connections and SDP negotiation."""

    def __init__(
        self,
        config_manager: ConfigManager,
        event_manager: EventManager | None = None,
        static_files_manager: StaticFilesManager | None = None,
    ) -> None:
        """Initialize the WebRTCManager."""
        self._config_manager = config_manager
        self._static_files_manager = static_files_manager
        self._upload_sessions: dict[str, UploadSession] = {}
        self._peer_connections: dict[str, RTCPeerConnection] = {}
        self._data_channels: dict[str, RTCDataChannel] = {}
        self._session_lock = threading.Lock()

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(WebRTCConnectRequest, self.handle_connection_offer_request)

    def _construct_static_file_url(self, filename: str) -> str:
        """Construct HTTP URL for static files.

        Args:
            filename: The filename (typically UUID-prefixed filename)

        Returns:
            HTTP URL in format: http://localhost:8124/workspace/staticfiles/{filename}
        """
        host = os.getenv("STATIC_SERVER_HOST", "localhost")
        port = os.getenv("STATIC_SERVER_PORT", "8124")

        # Get static files directory name from StaticFilesManager if available
        staticfiles_dir = "staticfiles"  # default
        if self._static_files_manager:
            resolved_directory = self._static_files_manager._get_static_files_directory()
            staticfiles_dir = Path(resolved_directory).name

        return f"http://{host}:{port}/workspace/{staticfiles_dir}/{filename}"

    def _extract_filename_from_url(self, file_id: str) -> str:
        """Extract filename from HTTP URL.

        Args:
            file_id: The file identifier (filename or HTTP URL)

        Returns:
            The extracted filename

        Raises:
            ValueError: If URL cannot be parsed or filename cannot be extracted
        """

        def _raise_extraction_error() -> None:
            msg = f"Cannot extract filename from URL: {file_id}"
            raise ValueError(msg)

        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(file_id)
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) >= 1:
                return path_parts[-1]  # Get the last part as filename
            _raise_extraction_error()
            return ""  # This line is never reached but satisfies type checker
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            msg = f"Failed to parse URL: {file_id} - {e}"
            raise ValueError(msg) from e

    async def handle_connection_offer_request(self, request: WebRTCConnectRequest) -> ResultPayload:
        """Handle WebRTC connection offer and generate SDP answer."""
        try:
            # Create peer connection with STUN server
            logger.info("Creating WebRTC peer connection for session %s", request.session_id)
            ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
            pc = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))

            # Store peer connection for session management
            session_key = f"{request.session_id}_{request.client_id}"
            with self._session_lock:
                self._peer_connections[session_key] = pc

            # Set up datachannel event handlers
            @pc.on("datachannel")
            def on_datachannel(channel: RTCDataChannel) -> None:
                logger.info("DataChannel '%s' opened for session %s", channel.label, request.session_id)

                if channel.label == "fileTransfer":
                    with self._session_lock:
                        self._data_channels[session_key] = channel

                    @channel.on("message")
                    def on_message(message: str) -> None:
                        task = asyncio.create_task(self._handle_datachannel_message(session_key, message))
                        # Store task reference to prevent garbage collection
                        task.add_done_callback(lambda _: None)

                    @channel.on("close")
                    def on_close() -> None:
                        logger.info("DataChannel closed for session %s", request.session_id)
                        with self._session_lock:
                            self._data_channels.pop(session_key, None)

            # Set remote description from offer
            logger.info("Setting remote description from offer for session %s", request.session_id)
            await pc.setRemoteDescription(RTCSessionDescription(sdp=request.offer_sdp, type="offer"))

            # Create and set local answer
            logger.info("Creating and setting local answer for session %s", request.session_id)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            return WebRTCConnectResultSuccess(
                session_id=request.session_id,
                client_id=request.client_id,
                answer_sdp=pc.localDescription.sdp,
                result_details="WebRTC connection established successfully",
            )

        except Exception as e:
            logger.error("WebRTC connection failed: %s", e)
            return WebRTCConnectResultFailure(result_details=f"WebRTC connection failed: {e}")

    async def _handle_datachannel_message(self, session_key: str, message: str) -> None:
        """Route datachannel messages to appropriate handlers based on message type."""
        try:
            # Parse message into structured type
            parsed_message = parse_message(message)

            # Route upload messages to upload handler
            if parsed_message.type in ["image_upload_start", "image_chunk", "image_upload_complete"]:
                # Type assertion for upload messages

                if isinstance(parsed_message, (ImageUploadStartMessage, ImageChunkMessage, ImageUploadCompleteMessage)):
                    await self._handle_file_upload_message(session_key, parsed_message)
                else:
                    logger.warning("Invalid upload message type: %s", type(parsed_message))
            # Route download messages to download handler
            elif parsed_message.type == "image_download_request":
                if isinstance(parsed_message, ImageDownloadRequestMessage):
                    await self._handle_download_request(session_key, parsed_message)
                else:
                    logger.warning("Invalid download message type: %s", type(parsed_message))
            else:
                logger.warning("Unknown message type: %s", parsed_message.type)

        except ValueError as e:
            logger.error("Error parsing datachannel message: %s", e)
            await self._send_upload_error(session_key, None, str(e))
        except Exception as e:
            logger.error("Error handling datachannel message: %s", e)
            await self._send_upload_error(session_key, None, str(e))

    async def _handle_file_upload_message(self, session_key: str, message: UploadMessage) -> None:
        """Handle file upload messages from WebRTC datachannel."""
        if not self._static_files_manager:
            logger.error("StaticFilesManager not available for file uploads")
            return

        try:
            if message.type == "image_upload_start":
                await self._handle_upload_start(session_key, message)
            elif message.type == "image_chunk":
                await self._handle_upload_chunk(session_key, message)
            elif message.type == "image_upload_complete":
                await self._handle_upload_complete(session_key, message)
            else:
                logger.warning("Unknown upload message type: %s", message.type)

        except Exception as e:
            logger.error("Error handling file upload message: %s", e)
            await self._send_upload_error(session_key, getattr(message, "fileId", None), str(e))

    async def _handle_upload_start(self, session_key: str, message: ImageUploadStartMessage) -> None:  # noqa: ARG002
        """Handle the start of a file upload."""
        # Validation checks
        if not message.fileType.startswith("image/"):
            msg = f"Invalid file type: {message.fileType}. Only images are supported via WebRTC."
            raise ValueError(msg)

        if message.totalBytes <= 0 or message.totalChunks <= 0:
            msg = "Invalid file size or chunk count"
            raise ValueError(msg)

        # Create upload session
        with self._session_lock:
            self._upload_sessions[message.fileId] = UploadSession(
                message.fileName, message.fileType, message.totalBytes, message.totalChunks
            )

        logger.info(
            "Started file upload: %s (%s bytes, %s chunks)", message.fileName, message.totalBytes, message.totalChunks
        )

    async def _handle_upload_chunk(self, session_key: str, message: ImageChunkMessage) -> None:  # noqa: ARG002
        """Handle a file chunk upload."""
        with self._session_lock:
            upload_session = self._upload_sessions.get(message.fileId)

        if not upload_session:
            msg = f"No upload session found for file ID: {message.fileId}"
            raise ValueError(msg)

        if message.chunkIndex < 0 or message.chunkIndex >= message.totalChunks:
            msg = f"Invalid chunk index: {message.chunkIndex}"
            raise ValueError(msg)

        if message.chunkIndex in upload_session.received_chunks:
            logger.warning("Duplicate chunk received: %s", message.chunkIndex)
            return

        # Validate chunk data is a string (Base64-encoded)
        if not isinstance(message.data, str):
            msg = f"Invalid chunk data type: expected string (Base64), got {type(message.data).__name__}"
            raise TypeError(msg)

        # Decode Base64 string back to bytes
        try:
            chunk_bytes = base64.b64decode(message.data)
        except Exception as e:
            msg = f"Failed to decode Base64 chunk data: {e}"
            raise ValueError(msg) from e
        upload_session.received_chunks[message.chunkIndex] = chunk_bytes

        logger.debug(
            "Received chunk %s/%s for file %s", message.chunkIndex + 1, message.totalChunks, upload_session.file_name
        )

    async def _handle_upload_complete(self, session_key: str, message: ImageUploadCompleteMessage) -> None:
        """Handle file upload completion and save the file."""
        with self._session_lock:
            upload_session = self._upload_sessions.get(message.fileId)

        if not upload_session:
            msg = f"No upload session found for file ID: {message.fileId}"
            raise ValueError(msg)

        # Validate all chunks were received
        if len(upload_session.received_chunks) != upload_session.total_chunks:
            missing_chunks = set(range(upload_session.total_chunks)) - set(upload_session.received_chunks.keys())
            msg = f"Missing chunks: {missing_chunks}"
            raise ValueError(msg)

        # Assemble file data from chunks
        upload_session.assembled_data = BytesIO()
        for i in range(upload_session.total_chunks):
            chunk = upload_session.received_chunks[i]
            upload_session.assembled_data.write(chunk)

        # Validate total size
        assembled_size = upload_session.assembled_data.tell()
        if assembled_size != upload_session.total_bytes:
            msg = f"Assembled size ({assembled_size}) does not match expected size ({upload_session.total_bytes})"
            raise ValueError(msg)

        # Generate unique filename to prevent conflicts
        file_path = Path(upload_session.file_name)
        unique_filename = f"{uuid.uuid4().hex}_{file_path.name}"

        # Save file directly for uploads (don't use save_static_file which returns download URLs)
        if not self._static_files_manager:
            msg = "StaticFilesManager not available"
            raise ValueError(msg)

        # Save file to storage using direct storage operations
        workspace_directory = Path(self._static_files_manager.config_manager.workspace_path)
        resolved_directory = self._static_files_manager._get_static_files_directory()
        storage_file_path = workspace_directory / resolved_directory / unique_filename

        upload_session.assembled_data.seek(0)
        file_data = upload_session.assembled_data.read()

        # Save file directly to storage location
        try:
            storage_file_path.write_bytes(file_data)
        except OSError as e:
            msg = f"Failed to save file {unique_filename}: {e}"
            logger.error(msg)
            raise ValueError(msg) from e

        # Create upload URL in HTTP format: http://localhost:8124/workspace/staticfiles/{fileId}_{fileName}
        upload_url = self._construct_static_file_url(unique_filename)

        # Send success response back through datachannel
        await self._send_upload_success(session_key, message.fileId, upload_url)

        # Clean up upload session
        with self._session_lock:
            self._upload_sessions.pop(message.fileId, None)

        logger.info("File upload completed successfully: %s -> %s", upload_session.file_name, upload_url)

    async def _handle_download_request(self, session_key: str, message: ImageDownloadRequestMessage) -> None:
        """Handle download request from frontend."""
        if not self._static_files_manager:
            logger.error("StaticFilesManager not available for file downloads")
            return

        try:
            # Construct full filename from fileId (UUID) and fileName (original name)
            full_filename = f"{message.fileId}_{message.fileName}"
            file_data, file_name, file_type = await self._load_file_for_download(full_filename)

            # Send download start message
            total_bytes = len(file_data)
            chunk_size = 16 * 1024  # 16KB chunks
            total_chunks = (total_bytes + chunk_size - 1) // chunk_size  # Math.ceil equivalent

            start_message = ImageDownloadStartMessage(
                type="image_download_start",
                fileId=message.fileId,
                requestId=message.requestId,
                fileName=file_name,
                fileType=file_type,
                totalBytes=total_bytes,
                totalChunks=total_chunks,
            )
            await self._send_datachannel_message(session_key, serialize_message(start_message))

            # Send file chunks
            for chunk_index in range(total_chunks):
                start_offset = chunk_index * chunk_size
                end_offset = min(start_offset + chunk_size, total_bytes)
                chunk_data = file_data[start_offset:end_offset]
                chunk_b64 = base64.b64encode(chunk_data).decode("utf-8")

                chunk_message = ImageDownloadChunkMessage(
                    type="image_download_chunk",
                    fileId=message.fileId,
                    requestId=message.requestId,
                    chunkIndex=chunk_index,
                    totalChunks=total_chunks,
                    data=chunk_b64,
                )
                await self._send_datachannel_message(session_key, serialize_message(chunk_message))

            # Send completion message
            complete_message = ImageDownloadCompleteMessage(
                type="image_download_complete", fileId=message.fileId, requestId=message.requestId
            )
            await self._send_datachannel_message(session_key, serialize_message(complete_message))

            logger.info("File download completed successfully: %s", file_name)

        except Exception as e:
            logger.error("Download request failed: %s", e)
            await self._send_download_error(session_key, message.fileId, message.requestId, str(e))

    async def _send_download_error(self, session_key: str, file_id: str, request_id: str, error_message: str) -> None:
        """Send download error response back through datachannel."""
        error_message_obj = ImageDownloadErrorMessage(
            type="image_download_error",
            fileId=file_id,
            requestId=request_id,
            error=error_message,
        )
        await self._send_datachannel_message(session_key, serialize_message(error_message_obj))

    async def _load_file_for_download(self, file_id: str) -> tuple[bytes, str, str]:
        """Load file data from fileId for WebRTC download.

        Args:
            file_id: The file identifier (filename or HTTP URL)

        Returns:
            Tuple of (file_data, file_name, file_type)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file_id is invalid
        """
        if not file_id or not isinstance(file_id, str):
            msg = f"Invalid file ID: {file_id}"
            raise ValueError(msg)

        # Extract filename from HTTP URL if necessary
        if file_id.startswith(("http://", "https://")):
            filename = self._extract_filename_from_url(file_id)
        else:
            filename = file_id

        # Validate filename format for security (no path traversal)
        if not filename.replace("_", "").replace("-", "").replace(".", "").isalnum():
            msg = f"Invalid filename format: {filename}"
            raise ValueError(msg)

        # Get static files directory (same logic as save_static_file)
        if not self._static_files_manager:
            msg = "StaticFilesManager not available"
            raise ValueError(msg)

        # Use same path construction as upload logic
        workspace_directory = Path(self._static_files_manager.config_manager.workspace_path)
        resolved_directory = self._static_files_manager._get_static_files_directory()
        file_path = workspace_directory / resolved_directory / filename

        # Check if file exists and is readable
        if not file_path.exists():
            msg = f"File not found: {filename}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {filename}"
            raise ValueError(msg)

        # Read file data
        try:
            file_data = file_path.read_bytes()
        except Exception as e:
            msg = f"Failed to read file {filename}: {e}"
            raise ValueError(msg) from e

        # Extract original filename from unique filename (format: {uuid}_{original_name})
        file_name = filename
        if "_" in filename:
            # Split on first underscore to get original name
            parts = filename.split("_", 1)
            if len(parts) == EXPECTED_PARTS_COUNT and len(parts[0]) == UUID_HEX_LENGTH:  # UUID hex length
                file_name = parts[1]

        # Determine MIME type from file extension
        file_suffix = Path(file_name).suffix.lower()
        mime_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        file_type = mime_type_map.get(file_suffix, "image/png")  # Default to PNG

        logger.info("Loaded file for download: %s (%d bytes, %s)", file_name, len(file_data), file_type)
        return file_data, file_name, file_type

    async def _send_upload_success(self, session_key: str, file_id: str, file_url: str) -> None:
        """Send upload success response back through datachannel."""
        success_message = UploadSuccessMessage(
            type="upload_success",
            fileId=file_id,
            url=file_url,
        )
        await self._send_datachannel_message(session_key, serialize_message(success_message))

    async def _send_upload_error(self, session_key: str, file_id: str | None, error_message: str) -> None:
        """Send upload error response back through datachannel."""
        error_message_obj = UploadErrorMessage(
            type="upload_error",
            fileId=file_id,
            error=error_message,
        )
        await self._send_datachannel_message(session_key, serialize_message(error_message_obj))

    async def _send_datachannel_message(self, session_key: str, message: str) -> None:
        """Send a message through the datachannel."""
        with self._session_lock:
            channel = self._data_channels.get(session_key)

        if channel and channel.readyState == "open":
            channel.send(message)
        else:
            logger.warning("DataChannel not available for session %s", session_key)
