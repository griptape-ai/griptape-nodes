from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
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
class RenameObjectResultSuccess(ResultPayloadSuccess):
    final_name: str  # May not be the same as what was requested, if that bool was set


@dataclass
@PayloadRegistry.register
class RenameObjectResultFailure(ResultPayloadFailure):
    next_available_name: str | None
