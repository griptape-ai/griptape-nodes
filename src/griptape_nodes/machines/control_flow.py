from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from griptape_nodes.app.app import event_queue
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.node_resolution import NodeResolutionMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowResolvedEvent,
)

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow

logger = logging.getLogger("griptape_nodes")


class ControlFlowContext:
    """Shared context containing information about whole flow execution."""

    flow: ControlFlow
    current_node: BaseNode | None
    resolution_machine: NodeResolutionMachine
    selected_output: Parameter | None
    paused: bool = False
    start_time: float | None  # Track flow start time

    def __init__(self) -> None:
        self.resolution_machine = NodeResolutionMachine()
        self.current_node = None
        self.start_time = None  # Initialize start time

    def get_next_node(self, output_parameter: Parameter) -> BaseNode | None:
        """Return the next node to execute."""
        if self.current_node is not None:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            node_connection = (
                GriptapeNodes.FlowManager().get_connections().get_connected_node(self.current_node, output_parameter)
            )
            if node_connection is not None:
                node, entry_parameter = node_connection
                return node
            # Get the next node in the execution queue, or None if queue is empty
            node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if node is not None:
                return node
        return None

    def reset(self) -> None:
        """Reset the context back to its initial state."""
        if self.current_node:
            self.current_node.clear_node()
        self.current_node = None
        self.resolution_machine.reset_machine()
        self.selected_output = None
        self.paused = False


class ResolveNodeState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        # The state machine has started, but it hasn't began to execute yet.
        if context.current_node is None:
            # We don't have anything else to do. Move back to Complete State so it has to restart.
            return CompleteState
        # Mark the node unresolved and notify GUI of the active control node
        context.current_node.make_node_unresolved(
            current_states_to_trigger_change_event=set(
                {
                    NodeResolutionState.UNRESOLVED,
                    NodeResolutionState.RESOLVED,
                    NodeResolutionState.RESOLVING,
                }
            )
        )
        logger.info("Resolving %s", context.current_node.name)
        if not context.paused:
            # Call the update. Otherwise wait
            return ResolveNodeState
        return None

    # This is necessary to transition to the next step.
    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:
        # If node has not already been resolved!
        if context.current_node is None:
            return CompleteState
        if context.current_node.state != NodeResolutionState.RESOLVED:
            context.resolution_machine.resolve_node(context.current_node)
        if context.resolution_machine.is_complete():
            return NextNodeState
        return None


class NextNodeState(State):
    """State that decides which node should be executed next."""

    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        if context.current_node is None:
            return CompleteState
        # I did define this on the ControlNode.
        if context.current_node.stop_flow:
            # We're done here.
            context.current_node.stop_flow = False
            return CompleteState
        next_output = context.current_node.get_next_control_output()
        if next_output is not None:
            context.selected_output = next_output
            next_node = context.get_next_node(context.selected_output)
        else:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            # Get the next node in the execution queue, or None if queue is empty
            next_node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if next_node is not None:
                return CompleteState
        context.current_node = next_node
        context.selected_output = None
        if not context.paused:
            return ResolveNodeState
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return ResolveNodeState


class CompleteState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        if context.current_node is not None:
            # Notify GUI that the flow is complete
            event_queue.put(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=ControlFlowResolvedEvent(
                            end_node_name=context.current_node.name,
                            parameter_output_values=TypeValidator.safe_serialize(
                                context.current_node.parameter_output_values
                            ),
                        )
                    )
                )
            )
        logger.info("Flow is complete.")
        # Log flow duration if start_time was recorded
        if context.start_time is not None:
            duration = time.time() - context.start_time
            logger.info("Flow took %.3f seconds.", duration)
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return None


class ControlFlowMachine(FSM[ControlFlowContext]):
    """Finite-state machine that resolves nodes in a flow graph."""

    def __init__(self) -> None:
        context = ControlFlowContext()
        super().__init__(context)

    def start_flow(self, start_node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        """Begin execution at start_node."""
        self._context.current_node = start_node
        # Record the start time for benchmarking
        self._context.start_time = time.time()
        # Set up to debug
        self._context.paused = debug_mode
        # Get the flow and make all nodes unresolved
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        parent_flow_str = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(start_node.name)
        parent_flow = None

        if parent_flow_str is not None:
            parent_flow = GriptapeNodes.FlowManager().get_flow_by_name(parent_flow_str)
            all_nodes = list(parent_flow.nodes.values())
            for node_to_unresolve in all_nodes:
                node_to_unresolve.make_node_unresolved(
                    {NodeResolutionState.RESOLVED, NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVING}
                )
        self.start(ResolveNodeState)  # Begins the flow

    def update(self) -> None:
        if self._current_state is None:
            msg = "Attempted to run the next step of a workflow that was either already complete or has not started."
            raise RuntimeError(msg)
        super().update()

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode
        self._context.resolution_machine.change_debug_mode(debug_mode=debug_mode)

    def granular_step(self, change_debug_mode: bool) -> None:  # noqa: FBT001
        """Resolve a single granular step and, optionally, enable debug mode."""
        resolution_machine = self._context.resolution_machine
        if change_debug_mode:
            resolution_machine.change_debug_mode(debug_mode=True)
        resolution_machine.update()

        # Tick the control flow if the resolution machine inside it isn't busy.
        if resolution_machine.is_complete() or not resolution_machine.is_started():  # noqa: SIM102
            # Don't tick ourselves if we are already complete.
            if self._current_state is not None:
                self.update()

    def node_step(self) -> None:
        """Resolve exactly one node and update the control-flow state."""
        resolution_machine = self._context.resolution_machine
        resolution_machine.change_debug_mode(debug_mode=False)
        resolution_machine.update()

        # Tick the control flow if the resolution machine inside it isn't busy.
        if resolution_machine.is_complete() or not resolution_machine.is_started():  # noqa: SIM102
            # Don't tick ourselves if we are already complete.
            if self._current_state is not None:
                self.update()

    def reset_machine(self) -> None:
        """Fully reset the state machine so that it can be re-used."""
        self._context.reset()
        self._current_state = None
