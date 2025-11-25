"""WebRTC events for peer-to-peer communication."""

from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


# WebRTC Connection Events
@dataclass
@PayloadRegistry.register
class WebRTCConnectRequest(RequestPayload):
    """Handle WebRTC connection offer with SDP data from frontend clients.

    Use when: Frontend initiates WebRTC peer connection, establishing direct
    communication channels, creating peer-to-peer data connections.

    Args:
        session_id: Unique session identifier for connection tracking
        client_id: Client identifier for offer/answer correlation
        offer_sdp: Session Description Protocol offer data from frontend

    Results: WebRTCConnectResultSuccess (with SDP answer) | WebRTCConnectResultFailure (invalid SDP, connection failure)
    """

    session_id: str
    client_id: str
    offer_sdp: str


@dataclass
@PayloadRegistry.register
class WebRTCConnectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """WebRTC connection offer processed successfully with SDP answer.

    Args:
        session_id: Session identifier matching the original request
        client_id: Client identifier matching the original request
        answer_sdp: Session Description Protocol answer data for frontend
    """

    session_id: str
    client_id: str
    answer_sdp: str


@dataclass
@PayloadRegistry.register
class WebRTCConnectResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """WebRTC connection offer processing failed.

    Common causes: malformed SDP data, WebRTC negotiation failure,
    invalid session/client identifiers, connection timeout.
    """
