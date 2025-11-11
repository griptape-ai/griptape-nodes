from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateDrawRequest(RequestPayload):
    """Create a new draw object.

    Args:
        requested_name: Desired name for the draw object (None for auto-generated)
        metadata: Initial metadata (can include x, y, width, height)
        x, y, width, height: Optional convenience fields to initialize position/size
    """

    requested_name: str | None = None
    metadata: dict[str, Any] | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


@dataclass
@PayloadRegistry.register
class CreateDrawResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    draw_name: str


@dataclass
@PayloadRegistry.register
class CreateDrawResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteDrawRequest(RequestPayload):
    """Delete a draw object by name."""

    draw_name: str


@dataclass
@PayloadRegistry.register
class DeleteDrawResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteDrawResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetDrawMetadataRequest(RequestPayload):
    """Retrieve metadata for a draw object."""

    draw_name: str


@dataclass
@PayloadRegistry.register
class GetDrawMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetDrawMetadataResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetDrawMetadataRequest(RequestPayload):
    """Merge metadata into an existing draw object."""

    draw_name: str
    metadata: dict[str, Any]


@dataclass
@PayloadRegistry.register
class SetDrawMetadataResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetDrawMetadataResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListDrawsRequest(RequestPayload):
    """List all draw object names."""


@dataclass
@PayloadRegistry.register
class ListDrawsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    draw_names: list[str] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class ListDrawsResultFailure(ResultPayloadFailure):
    pass


# -----------------------------------------------------------------------------
# Serialization (save like a node)
# -----------------------------------------------------------------------------


@dataclass
class SerializedDrawCommands:
    """Serialized commands required to recreate a draw object."""

    create_draw_command: CreateDrawRequest
    # Future: additional modification commands (currently unused)
    modification_commands: list[RequestPayload] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class SerializeDrawToCommandsRequest(RequestPayload):
    """Serialize a draw into a sequence of commands."""

    draw_name: str


@dataclass
@PayloadRegistry.register
class SerializeDrawToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    serialized_draw_commands: SerializedDrawCommands


@dataclass
@PayloadRegistry.register
class SerializeDrawToCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeserializeDrawFromCommandsRequest(RequestPayload):
    """Recreate a draw from serialized commands."""

    serialized_draw_commands: SerializedDrawCommands


@dataclass
@PayloadRegistry.register
class DeserializeDrawFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    draw_name: str


@dataclass
@PayloadRegistry.register
class DeserializeDrawFromCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
