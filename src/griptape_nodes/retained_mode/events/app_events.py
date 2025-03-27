from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AppSessionIDEstablished(AppPayload):
    session_id: str


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
class GetEngineVersion_Request(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetEngineVersionResult_Success(ResultPayload_Success):
    major: int
    minor: int
    patch: int


@dataclass
@PayloadRegistry.register
class GetEngineVersionResult_Failure(ResultPayload_Failure):
    pass
