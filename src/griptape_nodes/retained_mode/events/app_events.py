from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AppStartSessionRequest(RequestPayload):
    session_id: str


@dataclass
@PayloadRegistry.register
class AppStartSessionResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class AppStartSessionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class AppInitializationComplete(AppPayload):
    pass


@dataclass
@PayloadRegistry.register
class AppExecutionEvent(AppPayload):
    request: RequestPayload


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
class GetEngineVersionResultFailure(ResultPayloadFailure):
    pass
