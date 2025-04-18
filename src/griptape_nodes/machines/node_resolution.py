from __future__ import annotations

import logging
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING, Any

from griptape.events import EventBus
from griptape.utils import with_contextvars

from griptape_nodes.exe_types.core_types import ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
    ParameterSpotlightEvent,
    ParameterValueUpdateEvent,
    ResumeNodeProcessingEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import GetParameterDetailsRequest, SetParameterValueRequest

if TYPE_CHECKING:
    from griptape_nodes.exe_types.flow import ControlFlow


logger = logging.getLogger("griptape_nodes")


# This is on a per-node basis
class ResolutionContext:
    flow: ControlFlow
    focus_stack: list[BaseNode]
    paused: bool
    scheduled_value: Any | None
    future: Future | None
    shutdown_event: Event

    def __init__(self, flow: ControlFlow) -> None:
        self.flow = flow
        self.focus_stack = []
        self.paused = False
        self.scheduled_value = None
        self.future = None
        self.shutdown_event = Event()

    def reset(self) -> None:
        # Clear the nodes that is currently being worked on.
        if self.future:
            # Will only cancel if it hasn't started yet...
            if not self.future.cancel():
                # set the event to shut down the thread.
                self.shutdown_event.set()
            # Send an event to stop the GUI from taking threading tasks.
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=self.focus_stack[-1].name))
                )
            )
            # Clear the parameters? Since it'll be partially stored.
            for parameter in self.focus_stack[-1].parameters:
                if parameter.allowed_modes == {ParameterMode.OUTPUT}:
                    payload = ParameterValueUpdateEvent(
                        node_name=self.focus_stack[-1].name,
                        parameter_name=parameter.name,
                        data_type=parameter.type,
                        value=None,
                    )
                # Wipe current output of the parameter from the node please!
                    EventBus.publish_event(
                        ExecutionGriptapeNodeEvent(
                            wrapped_event=ExecutionEvent(payload=payload)
                        )
                    )
            self.executor = None
        if len(self.focus_stack) > 0:
            node = self.focus_stack[-1]
            node.clear_node()
        self.focus_stack = []
        self.paused = False
        self.scheduled_value = None


class InitializeSpotlightState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        # If the focus stack is empty
        context.shutdown_event.clear()
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
        if current_parameter is None:
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
    executor: ThreadPoolExecutor = ThreadPoolExecutor()

    # TODO(kate): Can we refactor this method to make it a lot cleaner? might involve changing how parameter values are retrieved/stored.
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: C901
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
            if parameter.name not in current_node.parameter_values:
                # If a parameter value is not already set
                value = current_node.get_parameter_value(parameter.name)
                if value is not None:
                    modified_parameters = current_node.set_parameter_value(parameter.name, value)
                    if modified_parameters:
                        for modified_parameter_name in modified_parameters:
                            # TODO(kate): Move to a different type of event

                            modified_request = GetParameterDetailsRequest(
                                parameter_name=modified_parameter_name, node_name=current_node.name
                            )
                            GriptapeNodes.handle_request(modified_request)
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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Once everything has been set
        current_node = context.focus_stack[-1]
        # To set the event manager without circular import errors
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
            )
        )
        logger.info("Node %s is processing.", current_node.name)

        try:
            work_is_scheduled = ExecuteNodeState._process_node(
                context=context,
                current_node=current_node,
            )
            if work_is_scheduled:
                logger.info("Pausing Node %s to run background work", current_node.name)
                return None
        except Exception as e:
            msg = f"Canceling flow run. Node '{current_node.name}' encountered a problem: {e}"
            current_node.state = NodeResolutionState.UNRESOLVED
            current_node.process_generator = None
            context.flow.cancel_flow_run()
            raise RuntimeError(msg) from e

        logger.info("Node %s finished processing.", current_node.name)

        # To set the event manager without circular import errors
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
            )
        )
        current_node.state = NodeResolutionState.RESOLVED
        details = f"{current_node.name} resolved."

        logger.info(details)

        # Serialization can be slow so only do it if the user wants debug details.
        if logger.level <= logging.DEBUG:
            logger.debug(
                "INPUTS: %s\nOUTPUTS: %s",
                TypeValidator.safe_serialize(current_node.parameter_values),
                TypeValidator.safe_serialize(current_node.parameter_output_values),
            )

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
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Canceling flow run. Node '{current_node.name}' specified a Parameter '{parameter_name}', but no such Parameter could be found on that Node."
                raise KeyError(err)
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
                        data_type=parameter.output_type,
                    )
                )
        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateParameterState
        return CompleteState

    @staticmethod
    def _process_node(context: ResolutionContext, current_node: BaseNode) -> bool:
        """Run the process method of the node.

        If the node's process method returns a generator, take the next value from the generator (a callable) and run
        that in a thread pool executor. The result of that callable will be passed to the generator when it is resumed.

        This has the effect of pausing at a yield expression, running the expression in a thread, and resuming when the thread pool is done.

        Args:
            context (ResolutionContext): The resolution context.
            current_node (BaseNode): The current node.

        Returns:
            bool: True if work has been scheduled, False if the node is done processing.
        """

        def on_future_done(future: Future) -> None:
            """Called when the future is done.

            Stores the result of the future in the node's context, and publishes an event to resume the flow.
            """
            context.scheduled_value = future.result()
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=ResumeNodeProcessingEvent(node_name=current_node.name))
                )
            )
            # Future no longer needs to be stored.
            context.future = None

        # Only start the processing if we don't already have a generator
        logger.debug("Node %s process generator: %s", current_node.name, current_node.process_generator)
        if current_node.process_generator is None:
            result = current_node.process()

            # If the process returned a generator, we need to store it for later
            if isinstance(result, Generator):
                current_node.process_generator = result
                logger.debug("Node %s returned a generator.", current_node.name)

        # We now have a generator, so we need to run it
        if current_node.process_generator is not None:
            try:
                logger.debug(
                    "Node %s has an active generator, sending scheduled value. Scheduled value is None: %s",
                    current_node.name,
                    context.scheduled_value is None,
                )
                func = current_node.process_generator.send(context.scheduled_value)
                # Once we've passed on the scheduled value, we should clear it out just in case
                context.scheduled_value = None
                future = ExecuteNodeState.executor.submit(with_contextvars(func), context.shutdown_event)
                future.add_done_callback(with_contextvars(on_future_done))
                context.future = future
            except StopIteration:
                logger.debug("Node %s generator is done.", current_node.name)
                # If that was the last generator, clear out the generator and indicate that there is no more work scheduled
                current_node.process_generator = None
                context.scheduled_value = None
                context.future = None
                return False
            else:
                # If the generator is not done, indicate that there is work scheduled
                logger.debug("Node %s generator is not done.", current_node.name)
                return True
        logger.debug("Node %s did not return a generator.", current_node.name)
        return False


class CompleteState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class NodeResolutionMachine(FSM[ResolutionContext]):
    """State machine for resolving node dependencies."""

    _context: ResolutionContext

    def __init__(self, flow: ControlFlow) -> None:
        self._context = ResolutionContext(flow)  # Gets the flow
        super().__init__(self._context)

    def resolve_node(self, node: BaseNode) -> None:
        self._context.focus_stack.append(node)
        self.start(InitializeSpotlightState)

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self) -> None:
        self._current_state = CompleteState
        self._context.reset()
