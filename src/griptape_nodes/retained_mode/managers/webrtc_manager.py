"""Manages WebRTC peer-to-peer connections using aiortc."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import uuid
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiortc import RTCConfiguration, RTCDataChannel, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from griptape_nodes.retained_mode.events.webrtc_events import (
    WebRTCConnectRequest,
    WebRTCConnectResultFailure,
    WebRTCConnectResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

logger = logging.getLogger("griptape_nodes")


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
                        task = asyncio.create_task(self._handle_file_upload_message(session_key, message))
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

    async def _handle_file_upload_message(self, session_key: str, message: str) -> None:
        """Handle file upload messages from WebRTC datachannel."""
        if not self._static_files_manager:
            logger.error("StaticFilesManager not available for file uploads")
            return

        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "image_upload_start":
                await self._handle_upload_start(session_key, data)
            elif message_type == "image_chunk":
                await self._handle_upload_chunk(session_key, data)
            elif message_type == "image_upload_complete":
                await self._handle_upload_complete(session_key, data)
            else:
                logger.warning("Unknown message type: %s", message_type)

        except Exception as e:
            logger.error("Error handling file upload message: %s", e)
            await self._send_error_response(session_key, str(e))

    async def _handle_upload_start(self, session_key: str, data: dict[str, Any]) -> None:  # noqa: ARG002
        """Handle the start of a file upload."""
        file_id = data["fileId"]
        file_name = data["fileName"]
        file_type = data["fileType"]
        total_bytes = data["totalBytes"]
        total_chunks = data["totalChunks"]

        # Validation checks
        if not file_type.startswith("image/"):
            msg = f"Invalid file type: {file_type}. Only images are supported via WebRTC."
            raise ValueError(msg)

        if total_bytes <= 0 or total_chunks <= 0:
            msg = "Invalid file size or chunk count"
            raise ValueError(msg)

        # Create upload session
        with self._session_lock:
            self._upload_sessions[file_id] = UploadSession(file_name, file_type, total_bytes, total_chunks)

        logger.info("Started file upload: %s (%s bytes, %s chunks)", file_name, total_bytes, total_chunks)

    async def _handle_upload_chunk(self, session_key: str, data: dict[str, Any]) -> None:  # noqa: ARG002
        """Handle a file chunk upload."""
        file_id = data["fileId"]
        chunk_index = data["chunkIndex"]
        total_chunks = data["totalChunks"]
        chunk_data = data["data"]  # Base64-encoded string

        with self._session_lock:
            upload_session = self._upload_sessions.get(file_id)

        if not upload_session:
            msg = f"No upload session found for file ID: {file_id}"
            raise ValueError(msg)

        if chunk_index < 0 or chunk_index >= total_chunks:
            msg = f"Invalid chunk index: {chunk_index}"
            raise ValueError(msg)

        if chunk_index in upload_session.received_chunks:
            logger.warning("Duplicate chunk received: %s", chunk_index)
            return

        # Validate chunk data is a string (Base64-encoded)
        if not isinstance(chunk_data, str):
            msg = f"Invalid chunk data type: expected string (Base64), got {type(chunk_data).__name__}"
            raise TypeError(msg)

        # Decode Base64 string back to bytes
        try:
            chunk_bytes = base64.b64decode(chunk_data)
        except Exception as e:
            msg = f"Failed to decode Base64 chunk data: {e}"
            raise ValueError(msg) from e
        upload_session.received_chunks[chunk_index] = chunk_bytes

        logger.debug("Received chunk %s/%s for file %s", chunk_index + 1, total_chunks, upload_session.file_name)

    async def _handle_upload_complete(self, session_key: str, data: dict[str, Any]) -> None:
        """Handle file upload completion and save the file."""
        file_id = data["fileId"]

        with self._session_lock:
            upload_session = self._upload_sessions.get(file_id)

        if not upload_session:
            msg = f"No upload session found for file ID: {file_id}"
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

        # Save file using StaticFilesManager
        if not self._static_files_manager:
            msg = "StaticFilesManager not available"
            raise ValueError(msg)

        upload_session.assembled_data.seek(0)
        file_data = upload_session.assembled_data.read()
        file_url = self._static_files_manager.save_static_file(file_data, unique_filename)

        # Send success response back through datachannel
        await self._send_success_response(session_key, file_url)

        # Clean up upload session
        with self._session_lock:
            self._upload_sessions.pop(file_id, None)

        logger.info("File upload completed successfully: %s -> %s", upload_session.file_name, file_url)

    async def _send_success_response(self, session_key: str, file_url: str) -> None:
        """Send success response back through datachannel."""
        response = {"type": "upload_success", "url": file_url}
        await self._send_datachannel_message(session_key, json.dumps(response))

    async def _send_error_response(self, session_key: str, error_message: str) -> None:
        """Send error response back through datachannel."""
        response = {"type": "upload_error", "error": error_message}
        await self._send_datachannel_message(session_key, json.dumps(response))

    async def _send_datachannel_message(self, session_key: str, message: str) -> None:
        """Send a message through the datachannel."""
        with self._session_lock:
            channel = self._data_channels.get(session_key)

        if channel and channel.readyState == "open":
            channel.send(message)
        else:
            logger.warning("DataChannel not available for session %s", session_key)
