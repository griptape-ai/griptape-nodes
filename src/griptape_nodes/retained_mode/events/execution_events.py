from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    ExecutionPayload,
    RequestPayload,
    ResultDetails,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

# Requests and Results TO/FROM USER! These begin requests - and are not fully Execution Events.


@dataclass
@PayloadRegistry.register
class ResolveNodeRequest(RequestPayload):
    """Resolve (execute) a specific node.

    Use when: Running individual nodes, testing node execution, debugging workflows,
    stepping through execution manually. Validates inputs and runs node logic.

    Args:
        node_name: Name of the node to resolve/execute
        debug_mode: Whether to run in debug mode (default: False)

    Results: ResolveNodeResultSuccess | ResolveNodeResultFailure (with validation exceptions)
    """

    node_name: str
    debug_mode: bool = False


@dataclass
@PayloadRegistry.register
class ResolveNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Node resolved successfully. Node execution completed and outputs are available."""


@dataclass
@PayloadRegistry.register
class ResolveNodeResultFailure(ResultPayloadFailure):
    """Node resolution failed. Contains validation errors that prevented execution.

    Args:
        validation_exceptions: List of validation errors that occurred
    """

    validation_exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class StartFlowRequest(RequestPayload):
    """Start executing a flow.

    Use when: Running workflows, beginning automated execution, testing complete flows.
    Validates all nodes and begins execution from resolved nodes.

    Args:
        flow_name: Name of the flow to start (deprecated, use flow_node_name)
        flow_node_name: Name of the flow node to start
        debug_mode: Whether to run in debug mode (default: False)

    Results: StartFlowResultSuccess | StartFlowResultFailure (with validation exceptions)
    """

    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None
    flow_node_name: str | None = None
    debug_mode: bool = False
    # If this is true, the final ControlFLowResolvedEvent will be pickled to be picked up from inside a subprocess.
    pickle_control_flow_result: bool = False


@dataclass
@PayloadRegistry.register
class StartFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow started successfully. Execution is now running."""


@dataclass
@PayloadRegistry.register
class StartFlowResultFailure(ResultPayloadFailure):
    """Flow start failed. Contains validation errors that prevented execution.

    Args:
        validation_exceptions: List of validation errors that occurred
    """

    validation_exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class StartFlowFromNodeRequest(RequestPayload):
    """Start executing a flow from a specific node.

    Use when: Resuming execution from a particular node, debugging specific parts of a flow,
    re-running portions of a workflow, implementing custom execution control.

    Args:
        flow_name: Name of the flow to start (deprecated)
        node_name: Name of the node to start execution from
        debug_mode: Whether to run in debug mode (default: False)
        pickle_control_flow_result: If this is true, the final ControlFLowResolvedEvent will be pickled to be picked up from inside a subprocess

    Results: StartFlowFromNodeResultSuccess | StartFlowFromNodeResultFailure (with validation exceptions)
    """

    flow_name: str | None = None
    node_name: str | None = None
    debug_mode: bool = False
    pickle_control_flow_result: bool = False


@dataclass
@PayloadRegistry.register
class StartFlowFromNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow started from node successfully. Execution is now running from the specified node."""


@dataclass
@PayloadRegistry.register
class StartFlowFromNodeResultFailure(ResultPayloadFailure):
    """Flow start from node failed. Contains validation errors that prevented execution.

    Args:
        validation_exceptions: List of validation errors that occurred
    """

    validation_exceptions: list[Exception]


@dataclass
@PayloadRegistry.register
class CancelFlowRequest(RequestPayload):
    """Cancel a running flow execution.

    Use when: Stopping long-running workflows, handling user cancellation,
    stopping execution due to errors or changes. Cleanly terminates execution.

    Args:
        flow_name: Name of the flow to cancel (deprecated)

    Results: CancelFlowResultSuccess | CancelFlowResultFailure (cancellation error)
    """

    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class CancelFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow cancelled successfully. Execution has been terminated."""


@dataclass
@PayloadRegistry.register
class CancelFlowResultFailure(ResultPayloadFailure):
    """Flow cancellation failed. Common causes: flow not running, cancellation error."""


@dataclass
@PayloadRegistry.register
class UnresolveFlowRequest(RequestPayload):
    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


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
    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


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
    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


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
    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


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
    """Get the current execution state of a flow.

    Use when: Monitoring execution progress, debugging workflow state,
    implementing execution UIs, checking which nodes are active.

    Results: GetFlowStateResultSuccess (with control/resolving nodes) | GetFlowStateResultFailure (flow not found)
    """

    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetFlowStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Flow execution state retrieved successfully.

    Args:
        control_nodes: Name of the current control node (if any)
        resolving_nodes: Name of the node currently being resolved (if any)
    """

    control_nodes: list[str]
    resolving_nodes: list[str]
    involved_nodes: list[str]


@dataclass
@PayloadRegistry.register
class GetFlowStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow state retrieval failed. Common causes: flow not found, no current context."""


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningRequest(RequestPayload):
    """Check if a flow is currently running.

    Use when: Monitoring execution status, preventing concurrent execution,
    implementing execution controls, checking if flow can be modified.

    Results: GetIsFlowRunningResultSuccess (with running status) | GetIsFlowRunningResultFailure (flow not found)
    """

    # Maintaining flow_name for backwards compatibility. Will be removed in https://github.com/griptape-ai/griptape-nodes/issues/1663
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Flow running status retrieved successfully.

    Args:
        is_running: Whether the flow is currently executing
    """

    is_running: bool


@dataclass
@PayloadRegistry.register
class GetIsFlowRunningResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow running status retrieval failed. Common causes: flow not found, no current context."""


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
    # Optional field for pickled parameter values - when present, parameter_output_values contains UUID references
    unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any] | None = field(
        default=None
    )


@dataclass
@PayloadRegistry.register
class ControlFlowCancelledEvent(ExecutionPayload):
    result_details: ResultDetails | str | None = None
    exception: Exception | None = None


@dataclass
@PayloadRegistry.register
class NodeResolvedEvent(ExecutionPayload):
    node_name: str
    parameter_output_values: dict
    node_type: str
    specific_library_name: str | None = None


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
class NodeFinishProcessEvent(ExecutionPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class InvolvedNodesEvent(ExecutionPayload):
    """Event indicating which nodes are involved in the current execution.

    For parallel resolution: Dynamic list based on DAG builder state
    For control flow/sequential: All nodes when started, empty when complete
    """

    involved_nodes: list[str]


@dataclass
@PayloadRegistry.register
class GriptapeEvent(ExecutionPayload):
    node_name: str
    parameter_name: str
    type: str
    value: Any
