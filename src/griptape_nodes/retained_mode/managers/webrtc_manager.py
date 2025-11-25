"""Manages WebRTC peer-to-peer connections using aiortc."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from griptape_nodes.retained_mode.events.webrtc_events import (
    WebRTCConnectRequest,
    WebRTCConnectResultFailure,
    WebRTCConnectResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class WebRTCManager:
    """Manages WebRTC peer connections and SDP negotiation."""

    def __init__(
        self,
        config_manager: ConfigManager,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize the WebRTCManager."""
        self._config_manager = config_manager

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(WebRTCConnectRequest, self.handle_connection_offer_request)

    async def handle_connection_offer_request(self, request: WebRTCConnectRequest) -> ResultPayload:
        """Handle WebRTC connection offer and generate SDP answer."""
        try:
            # Create peer connection with STUN server
            logger.info("Creating WebRTC peer connection for session %s", request.session_id)
            ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
            pc = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))

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
