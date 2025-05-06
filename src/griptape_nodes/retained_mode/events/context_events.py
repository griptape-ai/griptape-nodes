from dataclasses import dataclass

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
class SetWorkflowContextRequest(RequestPayload):
    workflow_name: str


@dataclass
@PayloadRegistry.register
class SetWorkflowContextSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetWorkflowContextFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetWorkflowContextRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetWorkflowContextSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    workflow_name: str | None


@dataclass
@PayloadRegistry.register
class GetWorkflowContextFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
