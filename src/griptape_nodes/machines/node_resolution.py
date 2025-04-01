from __future__ import annotations

from typing import TYPE_CHECKING

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import ParameterControlType, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.retained_mode.events.app_events import AppExecutionEvent
from griptape_nodes.retained_mode.events.base_events import AppEvent, ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
    ParameterSpotlightEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import GetParameterDetailsRequest

if TYPE_CHECKING:
    from griptape_nodes.exe_types.flow import ControlFlow


# This is on a per-node basis
class ResolutionContext:
    flow: ControlFlow
    focus_stack: list[BaseNode]
    paused: bool

    def __init__(self, flow: ControlFlow) -> None:
        self.flow = flow
        self.focus_stack = []
        self.paused = False


class InitializeSpotlightState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        # If the focus stack is empty
        current_node = context.focus_stack[-1]
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=current_node.name))
            )
        )
        if not context.paused:
            return InitializeSpotlightState
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        # If the focus stack is empty
        if not len(context.focus_stack):
            return CompleteState
        current_node = context.focus_stack[-1]
        if current_node.state == NodeResolutionState.UNRESOLVED:
            # Mark all future nodes unresolved.
            # TODO(griptape): Is this necessary? Should it be in these UNRESOLVED sections?
            context.flow.connections.unresolve_future_nodes(current_node)
            current_node.initialize_spotlight()
        # Set node to resolving - we are now resolving this node.
        current_node.state = NodeResolutionState.RESOLVING
        # Advance to next port if we do not have one ATM!
        if current_node.get_current_parameter() is None:
            # Advance to next port
            if current_node.advance_parameter():
                # if true, we advanced the port!
                return EvaluateParameterState
            # if not true, we have no ports left to advance to or none at all
            return ExecuteNodeState
        # We are already set here
        return EvaluateParameterState  # TODO(griptape): check if this is valid


class EvaluateParameterState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1]
        current_parameter = current_node.get_current_parameter()
        if not current_parameter:
            return ExecuteNodeState
        # if not in debug mode - keep going!
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=ParameterSpotlightEvent(
                        node_name=current_node.name,
                        parameter_name=current_parameter.name,
                    )
                )
            )
        )
        if not context.paused:
            return EvaluateParameterState
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1]
        current_parameter = current_node.get_current_parameter()
        connections = context.flow.connections
        if current_parameter is None:
            msg = "No current parameter set."
            raise ValueError(msg)
        # Get the next node
        next_node = connections.get_connected_node(current_node, current_parameter)
        if next_node:
            next_node, _ = next_node
        if next_node and next_node.state == NodeResolutionState.UNRESOLVED:
            # Already handles cycles with state
            context.focus_stack.append(next_node)
            return InitializeSpotlightState

        if current_node.advance_parameter():
            return InitializeSpotlightState
        return ExecuteNodeState


class ExecuteNodeState(State):
    # TODO(kate): Can we refactor this method to make it a lot cleaner? might involve changing how parameter values are retrieved/stored.
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: C901, PLR0912
        current_node = context.focus_stack[-1]
        connections = context.flow.connections
        # Get the parameters that have input values
        for parameter_name in current_node.parameter_output_values.copy():
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=ParameterValueUpdateEvent(
                            node_name=current_node.name,
                            parameter_name=parameter_name,
                            data_type="",
                            value=None,
                        )
                    )
                )
            )
            # This creates a new reference specifically for current_node
            current_node.parameter_output_values.pop(parameter_name)
        for parameter in current_node.parameters:
            if ParameterControlType.__name__ in parameter.allowed_types:
                continue
            use_set_value = False
            if ParameterMode.INPUT in parameter.allowed_modes:
                # If the parameter has an INPUT - This will be the value!
                source_values = connections.get_connected_node(current_node, parameter)
                if source_values:
                    source_node, source_port = source_values
                    # just check for node bc port doesn't matter
                    if source_node and source_port:
                        value = None
                        if source_port.name in source_node.parameter_output_values:
                            # This parameter output values is a dict for str and then parameters
                            value = source_node.parameter_output_values[source_port.name]
                        elif source_port.name in source_node.parameter_values:
                            value = source_node.parameter_values[source_port.name]
                        # Sets the value in the context!
                        if value:
                            modified_parameters = current_node.set_parameter_value(parameter.name, value)
                            if modified_parameters:
                                for modified_parameter_name in modified_parameters:
                                    modified_request = GetParameterDetailsRequest(
                                        parameter_name=modified_parameter_name, node_name=current_node.name
                                    )
                                    app_event = AppEvent(payload=AppExecutionEvent(modified_request))
                                    EventBus.publish_event(app_event)  # pyright: ignore[reportArgumentType]
                else:
                    use_set_value = ParameterMode.PROPERTY in parameter.allowed_modes
            # If the parameter DOES NOT have an input and has a property value- use the default value!
            elif ParameterMode.PROPERTY in parameter.allowed_modes:
                use_set_value = True

            if use_set_value and parameter.name not in current_node.parameter_values:
                # If a parameter value is not already set
                value = parameter.default_value
                modified_parameters = current_node.set_parameter_value(parameter.name, value)
                if modified_parameters:
                    for modified_parameter_name in modified_parameters:
                        # TODO(kate): Move to a different type of event
                        modified_request = GetParameterDetailsRequest(
                            parameter_name=modified_parameter_name, node_name=current_node.name
                        )
                        app_event = AppEvent(payload=AppExecutionEvent(modified_request))
                        EventBus.publish_event(app_event)  # pyright: ignore[reportArgumentType]
            if parameter.name in current_node.parameter_values:
                parameter_value = current_node.get_parameter_value(parameter.name)
                if isinstance(parameter_value, dict) and "type" in parameter_value:
                    data_type = parameter_value["type"]
                else:
                    data_type = type(parameter_value).__name__
                EventBus.publish_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=current_node.name,
                                parameter_name=parameter.name,
                                data_type=data_type,
                                value=TypeValidator.safe_serialize(parameter_value),
                            )
                        )
                    )
                )

        if not context.paused:
            return ExecuteNodeState
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        # Once everything has been set
        current_node = context.focus_stack[-1]
        # To set the event manager without circular import errors
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
            )
        )
        try:
            current_node.process()  # Pass in the NodeContext!
        except Exception as e:
            msg = f"Canceling flow run. Node '{current_node.name}' encountered a problem: {e}"
            current_node.state = NodeResolutionState.UNRESOLVED
            context.flow.cancel_flow_run()
            raise RuntimeError(msg) from e
        # To set the event manager without circular import errors
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
            )
        )
        current_node.state = NodeResolutionState.RESOLVED
        details = f"{current_node.name} resolved. \n Inputs: {TypeValidator.safe_serialize(current_node.parameter_values)} \n Outputs: {TypeValidator.safe_serialize(current_node.parameter_output_values)}"
        print(details)
        # Output values should already be saved!
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=NodeResolvedEvent(
                        node_name=current_node.name,
                        parameter_output_values=TypeValidator.safe_serialize(current_node.parameter_output_values),
                    )
                )
            )
        )
        for parameter, value in current_node.parameter_output_values.items():
            if hasattr(value, "type"):
                type_of = value.type
                EventBus.publish_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=current_node.name,
                                parameter_name=parameter,
                                data_type=str(type_of),
                                value=TypeValidator.safe_serialize(value),
                            )
                        ),
                    )
                )
            else:
                if isinstance(value, dict) and "type" in value:
                    data_type = value["type"]
                else:
                    data_type = type(value).__name__
                EventBus.publish_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=current_node.name,
                                parameter_name=parameter,
                                data_type=data_type,
                                value=TypeValidator.safe_serialize(value),
                            )
                        ),
                    )
                )

        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateParameterState
        return CompleteState


class CompleteState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class NodeResolutionMachine(FSM[ResolutionContext]):
    """State machine for resolving node dependencies."""

    def __init__(self, flow: ControlFlow) -> None:
        resolution_context = ResolutionContext(flow)  # Gets the flow
        super().__init__(resolution_context)

    def resolve_node(self, node: BaseNode) -> None:
        self._context.focus_stack.append(node)
        self.start(InitializeSpotlightState)

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_started(self) -> bool:
        return self._current_state is not None
