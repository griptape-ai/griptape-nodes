from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadFailureUnalteredWorkflow,
    ResultPayloadSuccess,
    ResultPayloadSuccessUnalteredWorkflow,
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
class AppGetSessionResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    session_id: str | None


@dataclass
@PayloadRegistry.register
class AppGetSessionResultFailure(ResultPayloadFailureUnalteredWorkflow):
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
class GetEngineVersionResultFailure(ResultPayloadSuccessUnalteredWorkflow):
    pass
