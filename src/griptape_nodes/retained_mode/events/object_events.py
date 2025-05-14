from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RenameObjectRequest(RequestPayload):
    object_name: str
    requested_name: str
    allow_next_closest_name_available: bool = False


@dataclass
@PayloadRegistry.register
class RenameObjectResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    final_name: str  # May not be the same as what was requested, if that bool was set


@dataclass
@PayloadRegistry.register
class RenameObjectResultFailure(ResultPayloadFailure):
    next_available_name: str | None


# This request will wipe all Flows, Nodes, Connections, everything.
# But you knew that, right? You knew what you were doing when you called it?
@dataclass
@PayloadRegistry.register
class ClearAllObjectStateRequest(RequestPayload):
    i_know_what_im_doing: bool = False


@PayloadRegistry.register
class ClearAllObjectStateResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class ClearAllObjectStateResultFailure(ResultPayloadFailure):
    pass
