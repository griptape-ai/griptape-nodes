from pydantic.dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class SetWorkflowContextRequest(RequestPayload):
    workflow_name: str


@PayloadRegistry.register
class SetWorkflowContextSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class SetWorkflowContextFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class GetWorkflowContextRequest(RequestPayload):
    pass


@PayloadRegistry.register
class GetWorkflowContextSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    workflow_name: str | None


@PayloadRegistry.register
class GetWorkflowContextFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
