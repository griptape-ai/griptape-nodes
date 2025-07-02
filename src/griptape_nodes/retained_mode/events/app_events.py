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
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1600
    session_id: str | None = None


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
class GetEngineVersionResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class AppEndSessionRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class AppEndSessionResultSuccess(ResultPayloadSuccess):
    session_id: str | None


@dataclass
@PayloadRegistry.register
class AppEndSessionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SessionHeartbeatRequest(RequestPayload):
    """Request clients can use ensure the engine session is still active."""


@dataclass
@PayloadRegistry.register
class SessionHeartbeatResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SessionHeartbeatResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class EngineHeartbeatRequest(RequestPayload):
    """Request clients can use to discover active engines and their status.

    Attributes:
        heartbeat_id: Unique identifier for the heartbeat request, used to correlate requests and responses.

    """

    heartbeat_id: str


@dataclass
@PayloadRegistry.register
class EngineHeartbeatResultSuccess(ResultPayloadSuccess):
    heartbeat_id: str
    engine_version: str
    engine_id: str | None
    session_id: str | None
    timestamp: str
    instance_type: str | None
    instance_region: str | None
    instance_provider: str | None
    deployment_type: str | None
    public_ip: str | None
    current_workflow: str | None
    workflow_file_path: str | None
    has_active_flow: bool
    engine_name: str


@dataclass
@PayloadRegistry.register
class EngineHeartbeatResultFailure(ResultPayloadFailure):
    heartbeat_id: str


@dataclass
@PayloadRegistry.register
class SetEngineNameRequest(RequestPayload):
    engine_name: str


@dataclass
@PayloadRegistry.register
class SetEngineNameResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    engine_name: str


@dataclass
@PayloadRegistry.register
class SetEngineNameResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error_message: str


@dataclass
@PayloadRegistry.register
class GetEngineNameRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetEngineNameResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    engine_name: str


@dataclass
@PayloadRegistry.register
class GetEngineNameResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error_message: str
