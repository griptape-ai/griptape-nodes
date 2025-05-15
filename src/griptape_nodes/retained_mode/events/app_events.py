from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class AppStartSessionRequest(RequestPayload):
    session_id: str


@PayloadRegistry.register
class AppStartSessionResultSuccess(ResultPayloadSuccess):
    session_id: str


@PayloadRegistry.register
class AppStartSessionResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class AppGetSessionRequest(RequestPayload):
    pass


@PayloadRegistry.register
class AppGetSessionResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    session_id: str | None


@PayloadRegistry.register
class AppGetSessionResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class AppInitializationComplete(AppPayload):
    pass


@PayloadRegistry.register
class GetEngineVersionRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetEngineVersionResultSuccess(ResultPayloadSuccess):
    major: int
    minor: int
    patch: int


@PayloadRegistry.register
class GetEngineVersionResultFailure(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass
