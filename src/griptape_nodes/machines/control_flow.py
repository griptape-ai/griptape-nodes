# Control flow machine
from __future__ import annotations

import logging
from threading import Thread
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

from griptape.events import EventBus
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.node_resolution import NodeResolutionMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowResolvedEvent,
    CurrentControlNodeEvent,
    SelectedControlOutputEvent,
)

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow

logger = logging.getLogger("griptape_nodes")


# This is the control flow context. Owns the Resolution Machine
class ControlFlowContext:
    flow: ControlFlow
    current_node: BaseNode | None
    resolution_machine: NodeResolutionMachine
    selected_output: Parameter | None
    paused: bool = False
    parallel_node_list: list[list[BaseNode]] = []

    def __init__(self, flow: ControlFlow) -> None:
        self.resolution_machine = NodeResolutionMachine(flow)
        self.flow = flow
        self.current_node = None
        self.parallel_node_list = []
        self.current_nodes: list[BaseNode] = []
        self.thread_pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
    def get_next_node(self, output_parameter: Parameter) -> BaseNode | None:
        if self.current_node is not None:
            node = self.flow.connections.get_connected_node(self.current_node, output_parameter)
            if node is not None:
                node, _ = node
            # Continue Execution to the next node that needs to be executed.
            elif not self.flow.flow_queue.empty():
                node = self.flow.flow_queue.get()
                self.flow.flow_queue.task_done()
            return node
        return None

    def reset(self) -> None:
        if self.current_node:
            self.current_node.clear_node()
        self.current_node = None
        self.resolution_machine.reset_machine()
        self.selected_output = None
        self.paused = False


# GOOD!
class ResolveNodeState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        # The state machine has started, but it hasn't began to execute yet.
        if context.current_node is None:
            # We don't have anything else to do. Move back to Complete State so it has to restart.
            return CompleteState

        # Mark the node unresolved, and broadcast an event to the GUI.
        context.current_node.make_node_unresolved(
            current_states_to_trigger_change_event=set(
                {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
            )
        )
        # Now broadcast that we have a current control node.
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentControlNodeEvent(node_name=context.current_node.name))
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
        next_node = None
        if next_output is not None:
            context.selected_output = next_output
            next_node = context.get_next_node(context.selected_output)
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=SelectedControlOutputEvent(
                            node_name=context.current_node.name,
                            selected_output_parameter_name=next_output.name,
                        )
                    )
                )
            )
        elif not context.flow.flow_queue.empty():
            next_node = context.flow.flow_queue.get()
            context.flow.flow_queue.task_done()
        # The parameter that will be evaluated next
        if next_node is None:
            # If no node attached
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
            EventBus.publish_event(
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
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return None


# MACHINE TIME!!!
class ControlFlowMachine(FSM[ControlFlowContext]):
    def __init__(self, flow: ControlFlow) -> None:
        context = ControlFlowContext(flow)
        super().__init__(context)

    def start_flow(self, start_node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        self._context.current_node = start_node
        # Set up to debug
        self._context.paused = debug_mode
        self.start(ResolveNodeState)  # Begins the flow

    def update(self) -> None:
        if self._current_state is None:
            msg = "Attempted to run the next step of a workflow that was either already complete or has not started."
            raise RuntimeError(msg)
        super().update()

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode
        self._context.resolution_machine.change_debug_mode(debug_mode)

    def granular_step(self, change_debug_mode: bool) -> None:  # noqa: FBT001
        resolution_machine = self._context.resolution_machine
        if change_debug_mode:
            resolution_machine.change_debug_mode(True)
        resolution_machine.update()

        # Tick the control flow if the resolution machine inside it isn't busy.
        if resolution_machine.is_complete() or not resolution_machine.is_started():  # noqa: SIM102
            # Don't tick ourselves if we are already complete.
            if self._current_state is not None:
                self.update()

    def node_step(self) -> None:
        resolution_machine = self._context.resolution_machine
        resolution_machine.change_debug_mode(False)
        resolution_machine.update()

        # Tick the control flow if the resolution machine inside it isn't busy.
        if resolution_machine.is_complete() or not resolution_machine.is_started():  # noqa: SIM102
            # Don't tick ourselves if we are already complete.
            if self._current_state is not None:
                self.update()

    def reset_machine(self) -> None:
        self._context.reset()
        self._current_state = None


class ParallelExecutionMachine(FSM[ControlFlowContext]):
    """
    State machine for managing parallel execution of nodes in a workflow.
    Framework only; parallel features and node selection logic to be added later.
    """
    
    def __init__(self, flow: ControlFlow) -> None:
        """Initialize with a reference to the flow object."""
        context = ControlFlowContext(flow)
        self.context: ControlFlowContext = context
        super().__init__(context)   # Thread pool for parallel execution
        self.thread_nodes: list[list[BaseNode]] = [[], [], [], []]
        self._current_state: State | None = None
        self.flow: ControlFlow = flow
    def start_flow_parallel(self) -> None:
        """Start the parallel execution process."""
        # Initialize thread pool for parallel execution
        node_list: list[BaseNode] = list(self.flow.nodes.values())
        thread_run_value: str = ""

        for node in node_list:
            thread_run_value = node.get_parameter_value("thread_run")
            if thread_run_value == "1":
                self.thread_nodes[0].append(node)
            elif thread_run_value == "2":
                self.thread_nodes[1].append(node)
            elif thread_run_value == "3":
                self.thread_nodes[2].append(node)
            else:
                self.thread_nodes[3].append(node)
        self._context.parallel_node_list = self.thread_nodes
        self.start(ParallelNextNodeState)
        logger.info("Starting parallel execution machine")
        
    def update(self) -> None:
        """Advance the parallel execution state machine by one step."""

        # Check if any parallel tasks have completed
        if self._current_state is None:
            msg = "Attempted to run the next step of a workflow that was either already complete or has not started."
            raise RuntimeError(msg)
        super().update()
        # TODO: Add logic to start new parallel tasks when dependencies are met
        # TODO: Add logic to transition between parallel states

    def complete(self) -> None:
        """Mark the parallel execution as complete."""
        # Wait for all active futures to complete
        
        # Shutdown thread pool
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None
        logger.info("Parallel execution machine completed")


class ParallelResolveNodeState(State):
    """State for resolving nodes in parallel execution."""
    
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        """Called when entering the parallel resolve node state."""
        logger.debug("Entering parallel resolve node state")
        for node in context.current_nodes:
            
        return None

    @staticmethod
    def on_update(context: Any) -> type[State] | None:
        """Called when updating the parallel resolve node state."""
        
        logger.debug("Updating parallel resolve node state")
        return ResolveNodeState

    @staticmethod
    def on_exit(context: Any) -> None:
        """Called when exiting the parallel resolve node state."""
        logger.debug("Exiting parallel resolve node state")


class ParallelNextNodeState(State):
    """State for resolving nodes in parallel execution."""
    
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        """Called when entering the parallel next node state."""
        if not context.current_nodes:
            for node_list in context.parallel_node_list:
                for node in node_list:
                    if not context.flow.get_connected_input_from_node(node):
                        context.current_nodes.append(node)
                        break
        else:
            new_current_nodes = []
            for node in context.current_nodes:
                connections = context.flow.get_control_output_connections(node)
                for connection in connections:
                    if connection.target_node not in context.current_nodes:
                        new_current_nodes.append(connection.target_node)
            context.current_nodes = new_current_nodes
        logger.debug("Entering parallel next node state")
        return ParallelResolveNodeState

    @staticmethod
    def on_update(context: Any) -> type[State] | None:
        """Called when updating the parallel next node state."""
        return ParallelResolveNodeState

    @staticmethod
    def on_exit(context: Any) -> None:
        """Called when exiting the parallel next node state."""
        logger.debug("Exiting parallel next node state")
