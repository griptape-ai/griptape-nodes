from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class LogHandlerEvent(AppPayload):
    message: str
    levelname: str
    created: float
