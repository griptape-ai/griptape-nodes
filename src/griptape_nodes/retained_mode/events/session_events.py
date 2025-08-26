"""Events for session management and client registration."""

from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RegisterSessionClientRequest(RequestPayload):
    """Request registration of a new session client.

    Results: RegisterSessionClientResultSuccess | RegisterSessionClientResultFailure
    """


@dataclass
@PayloadRegistry.register
class RegisterSessionClientResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Client ID assigned successfully.

    Args:
        client_id: Unique client identifier assigned by the orchestrator
    """

    client_id: str


@dataclass
@PayloadRegistry.register
class RegisterSessionClientResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Client registration failed."""
