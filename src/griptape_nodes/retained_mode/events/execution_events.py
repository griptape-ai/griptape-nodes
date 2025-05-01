from dataclasses import dataclass
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    ExecutionPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

# Requests and Results TO/FROM USER! These begin requests - and are not fully Execution Events.


@dataclass
@PayloadRegistry.register
class ResolveNodeRequest(RequestPayload):
    node_name: str
    debug_mode: bool = False


@dataclass
@PayloadRegistry.register
class ResolveNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ResolveNodeResultFailure(ResultPayloadFailure):
    validation_exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class StartFlowRequest(RequestPayload):
    flow_name: str
    flow_node_name: str | None = None
    debug_mode: bool = False


@dataclass
@PayloadRegistry.register
class StartFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class StartFlowResultFailure(ResultPayloadFailure):
    validation_exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class CancelFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class CancelFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class CancelFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class UnresolveFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class UnresolveFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class UnresolveFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


# User Tick Events


# Step In: Execute one resolving step at a time (per parameter)
@dataclass
@PayloadRegistry.register
class SingleExecutionStepRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class SingleExecutionStepResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class SingleExecutionStepResultFailure(ResultPayloadFailure):
    pass


# Step Over: Execute one node at a time (execute whole node and move on) IS THIS CONTROL NODE OR ANY NODE?
@dataclass
@PayloadRegistry.register
class SingleNodeStepRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class SingleNodeStepResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SingleNodeStepResultFailure(ResolveNodeResultFailure):
    pass


# Continue
@dataclass
@PayloadRegistry.register
class ContinueExecutionStepRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class ContinueExecutionStepResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ContinueExecutionStepResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetFlowStateRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class GetFlowStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    control_node: str | None
    resolving_node: str | None


@dataclass
@PayloadRegistry.register
class GetFlowStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    is_running: bool


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# Execution Events! These are sent FROM the EE to the User/GUI. HOW MANY DO WE NEED?
@dataclass
@PayloadRegistry.register
class CurrentControlNodeEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class CurrentDataNodeEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class SelectedControlOutputEvent(ExecutionPayload):
    node_name: str
    selected_output_parameter_name: str


@dataclass
@PayloadRegistry.register
class ParameterSpotlightEvent(ExecutionPayload):
    node_name: str
    parameter_name: str


@dataclass
@PayloadRegistry.register
class ControlFlowResolvedEvent(ExecutionPayload):
    end_node_name: str
    parameter_output_values: dict


@dataclass
@PayloadRegistry.register
class ControlFlowCancelledEvent(ExecutionPayload):
    pass


@dataclass
@PayloadRegistry.register
class NodeResolvedEvent(ExecutionPayload):
    node_name: str
    parameter_output_values: dict


@dataclass
@PayloadRegistry.register
class ParameterValueUpdateEvent(ExecutionPayload):
    node_name: str
    parameter_name: str
    data_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class NodeUnresolvedEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class NodeStartProcessEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class ResumeNodeProcessingEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class NodeFinishProcessEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class GriptapeEvent(ExecutionPayload):
    node_name: str
    parameter_name: str
    type: str
    value: Any
