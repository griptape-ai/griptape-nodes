from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AppStartSessionRequest(RequestPayload):
    session_id: str


@dataclass
@PayloadRegistry.register
class AppStartSessionResultSuccess(ResultPayloadSuccess):
    session_id: str


@dataclass
@PayloadRegistry.register
class AppStartSessionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class AppGetSessionRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class AppGetSessionResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    session_id: str | None


@dataclass
@PayloadRegistry.register
class AppGetSessionResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class AppInitializationComplete(AppPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetEngineVersionRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetEngineVersionResultSuccess(ResultPayloadSuccess):
    major: int
    minor: int
    patch: int


@dataclass
@PayloadRegistry.register
class GetEngineVersionResultFailure(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass
