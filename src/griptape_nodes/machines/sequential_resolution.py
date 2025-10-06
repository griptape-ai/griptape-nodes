from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from griptape_nodes.exe_types.connections import Direction
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
    ParameterSpotlightEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


@dataclass
class Focus:
    node: BaseNode
    task: asyncio.Task[None] | None = None


# This is on a per-node basis
class ResolutionContext:
    focus_stack: list[Focus]
    paused: bool

    def __init__(self) -> None:
        self.focus_stack = []
        self.paused = False

    @property
    def current_node(self) -> BaseNode:
        """Get the currently focused node from the focus stack."""
        if not self.focus_stack:
            msg = "No node is currently in focus - focus stack is empty"
            raise RuntimeError(msg)
        return self.focus_stack[-1].node

    def reset(self) -> None:
        if self.focus_stack:
            node = self.focus_stack[-1].node
            # clear the data node being resolved.
            node.clear_node()
        self.focus_stack.clear()
        self.paused = False


class InitializeSpotlightState(State):
    @staticmethod
    async def on_enter(context: ResolutionContext) -> type[State] | None:
        # If the focus stack is empty
        if not context.paused:
            return InitializeSpotlightState
        return None

    @staticmethod
    async def on_update(context: ResolutionContext) -> type[State] | None:
        # If the focus stack is empty
        if not len(context.focus_stack):
            return CompleteState
        current_node = context.current_node
        if current_node.state == NodeResolutionState.UNRESOLVED:
            # Mark all future nodes unresolved.
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/862
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.FlowManager().get_connections().unresolve_future_nodes(current_node)
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
        return EvaluateParameterState  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/863


class EvaluateParameterState(State):
    @staticmethod
    async def on_enter(context: ResolutionContext) -> type[State] | None:
        current_node = context.current_node
        current_parameter = current_node.get_current_parameter()
        if current_parameter is None:
            return ExecuteNodeState
        # if not in debug mode - keep going!
        GriptapeNodes.EventManager().put_event(
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
    async def on_update(context: ResolutionContext) -> type[State] | None:
        current_node = context.current_node
        current_parameter = current_node.get_current_parameter()
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        if current_parameter is None:
            msg = "No current parameter set."
            raise ValueError(msg)
        # Get the next node
        next_node = connections.get_connected_node(current_node, current_parameter)
        if next_node:
            next_node, _ = next_node
        if next_node and next_node.state == NodeResolutionState.UNRESOLVED:
            focus_stack_names = {focus.node.name for focus in context.focus_stack}
            if next_node.name in focus_stack_names:
                msg = f"Cycle detected between node '{current_node.name}' and '{next_node.name}'."
                raise RuntimeError(msg)

            context.focus_stack.append(Focus(node=next_node))
            return InitializeSpotlightState

        if current_node.advance_parameter():
            return InitializeSpotlightState
        return ExecuteNodeState


class ExecuteNodeState(State):
    @staticmethod
    async def collect_values_from_upstream_nodes(context: ResolutionContext) -> None:
        """Collect output values from resolved upstream nodes and pass them to the current node.

        This method iterates through all input parameters of the current node, finds their
        connected upstream nodes, and if those nodes are resolved, retrieves their output
        values and passes them through using SetParameterValueRequest.

        Args:
            context (ResolutionContext): The resolution context containing the focus stack
                with the current node being processed.
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        current_node = context.current_node
        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            # Get the connected upstream node for this parameter
            upstream_connection = connections.get_connected_node(current_node, parameter, direction=Direction.UPSTREAM)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # If the upstream node is resolved, collect its output value
                if upstream_parameter.name in upstream_node.parameter_output_values:
                    output_value = upstream_node.parameter_output_values[upstream_parameter.name]
                else:
                    output_value = upstream_node.get_parameter_value(upstream_parameter.name)

                # Pass the value through using the same mechanism as normal resolution
                result = GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=parameter.name,
                        node_name=current_node.name,
                        value=output_value,
                        data_type=upstream_parameter.output_type,
                        incoming_connection_source_node_name=upstream_node.name,
                        incoming_connection_source_parameter_name=upstream_parameter.name,
                    )
                )
                if isinstance(result, SetParameterValueResultFailure):
                    msg = f"Failed to set parameter value for node '{current_node.name}' and parameter '{parameter.name}'. Details: {result.result_details}"
                    logger.error(msg)
                    raise RuntimeError(msg)

    @staticmethod
    async def on_enter(context: ResolutionContext) -> type[State] | None:
        current_node = context.current_node

        # Clear all of the current output values
        # if node is locked, don't clear anything. skip all of this.
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=current_node.name))
            )
        )
        if current_node.lock:
            return ExecuteNodeState
        await ExecuteNodeState.collect_values_from_upstream_nodes(context)

        # Clear all of the current output values but don't broadcast the clearing.
        # to avoid any flickering in subscribers (UI).
        context.current_node.parameter_output_values.silent_clear()

        for parameter in current_node.parameters:
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue
            if parameter.name not in current_node.parameter_values:
                # If a parameter value is not already set
                value = current_node.get_parameter_value(parameter.name)
                if value is not None:
                    current_node.set_parameter_value(parameter.name, value)

            if parameter.name in current_node.parameter_values:
                parameter_value = current_node.get_parameter_value(parameter.name)
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                GriptapeNodes.EventManager().put_event(
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

        exceptions = current_node.validate_before_node_run()
        if exceptions:
            msg = f"Canceling flow run. Node '{current_node.name}' encountered problems: {exceptions}"
            # Mark the node as unresolved, broadcasting to everyone.
            raise RuntimeError(msg)
        if not context.paused:
            return ExecuteNodeState
        return None

    @staticmethod
    async def on_update(context: ResolutionContext) -> type[State] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Once everything has been set
        current_focus = context.focus_stack[-1]
        current_node = current_focus.node
        # If the node is not locked, execute all of this.
        if not current_node.lock:
            # To set the event manager without circular import errors
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
                )
            )
            logger.info("Node '%s' is processing.", current_node.name)
            current_node = current_focus.node

            try:
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                executor = GriptapeNodes.FlowManager().node_executor
                # Create and track task in Focus for cancellation support
                execution_task = asyncio.create_task(executor.execute(current_node))
                current_focus.task = execution_task
                await execution_task
            except asyncio.CancelledError:
                logger.info("Node '%s' processing was cancelled.", current_node.name)
                current_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                    )
                )
                GriptapeNodes.EventManager().put_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                    )
                )
                return CompleteState
            except Exception as e:
                logger.exception("Error processing node '%s", current_node.name)
                msg = f"Canceling flow run. Node '{current_node.name}' encountered a problem: {e}"
                # Mark the node as unresolved, broadcasting to everyone.
                current_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                    )
                )

                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                await GriptapeNodes.FlowManager().cancel_flow_run()

                GriptapeNodes.EventManager().put_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                    )
                )
                raise RuntimeError(msg) from e

            logger.info("Node '%s' finished processing.", current_node.name)

            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                )
            )
            current_node.state = NodeResolutionState.RESOLVED
            details = f"'{current_node.name}' resolved."

            logger.info(details)

            # Serialization can be slow so only do it if the user wants debug details.
            if logger.level <= logging.DEBUG:
                logger.debug(
                    "INPUTS: %s\nOUTPUTS: %s",
                    TypeValidator.safe_serialize(current_node.parameter_values),
                    TypeValidator.safe_serialize(current_node.parameter_output_values),
                )

            for parameter_name, value in current_node.parameter_output_values.items():
                parameter = current_node.get_parameter_by_name(parameter_name)
                if parameter is None:
                    err = f"Canceling flow run. Node '{current_node.name}' specified a Parameter '{parameter_name}', but no such Parameter could be found on that Node."
                    raise KeyError(err)
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                GriptapeNodes.EventManager().put_event(
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
            # Output values should already be saved!
        library = LibraryRegistry.get_libraries_with_node_type(current_node.__class__.__name__)
        if len(library) == 1:
            library_name = library[0]
        else:
            library_name = None
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=NodeResolvedEvent(
                        node_name=current_node.name,
                        parameter_output_values=TypeValidator.safe_serialize(current_node.parameter_output_values),
                        node_type=current_node.__class__.__name__,
                        specific_library_name=library_name,
                    )
                )
            )
        )
        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateParameterState

        return CompleteState


class CompleteState(State):
    @staticmethod
    async def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

    @staticmethod
    async def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class SequentialResolutionMachine(FSM[ResolutionContext]):
    """State machine for resolving node dependencies."""

    def __init__(self) -> None:
        resolution_context = ResolutionContext()
        super().__init__(resolution_context)

    async def resolve_node(self, node: BaseNode | None = None) -> None:
        if node is None:
            msg = "SequentialResolutionMachine requires a node to resolve"
            raise ValueError(msg)
        self._context.focus_stack.append(Focus(node=node))
        await self.start(InitializeSpotlightState)

    async def cancel_all_nodes(self) -> None:
        """Cancel the currently executing node and set cancellation flags on all nodes in focus stack."""
        # Set cancellation flag on all nodes in the focus stack
        for focus in self._context.focus_stack:
            focus.node.request_cancellation()

        # Collect tasks that need to be cancelled
        tasks = []
        if self._context.focus_stack:
            current_focus = self._context.focus_stack[-1]
            if current_focus.task and not current_focus.task.done():
                tasks.append(current_focus.task)

        # Cancel all tasks
        for task in tasks:
            task.cancel()

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    # Unused argument but necessary for parallel_resolution because of futures ending during cancel but not reset.
    def reset_machine(self, *, cancel: bool = False) -> None:  # noqa: ARG002
        self._context.reset()
        self._current_state = None
