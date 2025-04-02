from __future__ import annotations

from typing import TYPE_CHECKING

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
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
from griptape_nodes.retained_mode.events.parameter_events import GetParameterDetailsRequest, SetParameterValueRequest

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
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: C901
        current_node = context.focus_stack[-1]
        # Get the parameters that have input values
        for parameter_name in current_node.parameter_output_values.copy():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Attempted to execute node '{current_node.name}' but could not find parameter '{parameter_name}' that was indicated as having a value."
                raise ValueError(err)
            parameter_type = parameter.type
            if parameter_type is None:
                parameter_type = ParameterTypeBuiltin.NONE.value
            payload = ParameterValueUpdateEvent(
                node_name=current_node.name,
                parameter_name=parameter_name,
                data_type=parameter_type,
                value=None,
            )
            EventBus.publish_event(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
        for parameter in current_node.parameters:
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue
            if parameter.name not in current_node.parameter_values and parameter.default_value:
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
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                EventBus.publish_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=current_node.name,
                                parameter_name=parameter.name,
                                # this is because the type is currently IN the parameter.
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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger

        logger.info(details)
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
        for parameter_name, value in current_node.parameter_output_values.items():
            data_type = None
            if hasattr(value, "type"):
                data_type = str(value.type)
            elif isinstance(value, dict) and "type" in value:
                data_type = value["type"]
            else:
                data_type = type(value).__name__
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Canceling flow run. Node '{current_node.name}' specified a Parameter '{parameter_name}', but no such Parameter could be found on that Node."
                raise KeyError(err)
            if not parameter.is_outgoing_type_allowed(data_type):
                msg = f"Type of {data_type} does not match the output type of {parameter.output_type} for parameter '{parameter_name}'."
                logger.warning(msg)
            data_type = parameter.type
            if data_type is None:
                data_type = ParameterTypeBuiltin.NONE.value
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=ParameterValueUpdateEvent(
                            node_name=current_node.name,
                            parameter_name=parameter_name,
                            data_type=data_type,
                            value=TypeValidator.safe_serialize(value),
                        )
                    ),
                )
            )
            # Pass the value through to the new nodes.
            conn_output_nodes = context.flow.get_connected_output_parameters(current_node, parameter)
            for target_node, target_parameter in conn_output_nodes:
                GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=target_parameter.name,
                        node_name=target_node.name,
                        value=value,
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
