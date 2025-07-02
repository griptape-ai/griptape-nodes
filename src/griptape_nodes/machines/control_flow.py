# Control flow machine
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape.events import EventBus
from concurrent.futures import ThreadPoolExecutor
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

    def __init__(self, flow: ControlFlow) -> None:
        self.resolution_machine = NodeResolutionMachine(flow)
        self.flow = flow
        self.current_node = None

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


class ParallelProcessingState(State):
    """
    State for handling parallel processing of nodes.
    Manages concurrent execution, dependency tracking, and completion detection.
    """
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        """Called when entering parallel processing state."""
        if context.current_node is None:
            return CompleteState
        
        # Mark the node as being processed in parallel
        context.current_node.make_node_unresolved(
            current_states_to_trigger_change_event={
                NodeResolutionState.UNRESOLVED,
                NodeResolutionState.RESOLVED,
                NodeResolutionState.RESOLVING
            }
        )
        
        # Broadcast that we're starting parallel processing
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=CurrentControlNodeEvent(node_name=context.current_node.name)
                )
            )
        )
        
        logger.info("Starting parallel processing for %s", context.current_node.name)
        
        if not context.paused:
            return ParallelProcessingState
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:
        """Called each update to advance parallel processing."""
        if context.current_node is None:
            return CompleteState
        
        # TODO: Add parallel processing logic here
        # 1. Check if current node is ready for parallel execution
        # 2. Start parallel execution if not already started
        # 3. Monitor parallel execution progress
        # 4. Check if parallel execution is complete
        
        # Placeholder: For now, just transition to NextNodeState
        # In the actual implementation, you would:
        # - Use ThreadPoolExecutor or ProcessPoolExecutor
        # - Track futures and their completion
        # - Handle parallel dependency resolution
        # - Manage parallel error handling
        
        logger.info("Parallel processing complete for %s", context.current_node.name)
        return NextNodeState


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


class ParallelExecutionMachine:
    """
    State machine for managing parallel execution of nodes in a workflow.
    Framework only; parallel features and node selection logic to be added later.
    """
    def __init__(self, flow):
        """Initialize with a reference to the flow object."""
        self.flow = flow
        self._current_state = None
        self._context = None
        self._active_futures = {}  # Track running parallel tasks
        self._thread_pool = None   # Thread pool for parallel execution
        self._thread_states = {}   # Track state for each thread/node

    def start(self, start_node=None, debug_mode=False):
        """Start the parallel execution process."""
        # Initialize thread pool for parallel execution
        self._thread_pool = ThreadPoolExecutor(max_workers=4)
        
        # Set up initial state for parallel execution
        self._current_state = "parallel_initializing"
        self._active_futures = {}
        self._thread_states = {}
        
        logger.info("Starting parallel execution machine")
        
        # TODO: Initialize parallel context and start first parallel batch

    def update(self):
        """Advance the parallel execution state machine by one step."""
        if self._current_state is None:
            return

        # Check if any parallel tasks have completed
        completed_futures = []
        for node_name, future in self._active_futures.items():
            if future.done():
                completed_futures.append(node_name)
                try:
                    result = future.result()
                    logger.info(f"Parallel task {node_name} completed successfully")
                    # Update thread state to completed
                    self._thread_states[node_name] = "completed"
                except Exception as e:
                    logger.error(f"Parallel task {node_name} failed: {e}")
                    # Update thread state to failed
                    self._thread_states[node_name] = "failed"
        
        # Remove completed futures
        for node_name in completed_futures:
            del self._active_futures[node_name]
        
        # Update state for each active thread
        for node_name in self._active_futures.keys():
            if node_name not in self._thread_states:
                self._thread_states[node_name] = "running"
            elif self._thread_states[node_name] == "initializing":
                self._thread_states[node_name] = "running"
        
        # TODO: Add logic to start new parallel tasks when dependencies are met
        # TODO: Add logic to transition between parallel states
        
        logger.debug(f"Parallel execution update: {len(self._active_futures)} active tasks")
        logger.debug(f"Thread states: {self._thread_states}")

    def complete(self):
        """Mark the parallel execution as complete."""
        # Wait for all active futures to complete
        if self._active_futures:
            logger.info(f"Waiting for {len(self._active_futures)} parallel tasks to complete")
            for future in self._active_futures.values():
                future.result()  # This will raise any exceptions
        
        # Shutdown thread pool
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
            self._thread_pool = None
        
        self._current_state = None
        self._active_futures = {}
        self._thread_states = {}
        logger.info("Parallel execution machine completed")

    def get_thread_state(self, node_name):
        """Get the current state of a specific thread/node."""
        return self._thread_states.get(node_name, "unknown")

    def set_thread_state(self, node_name, state):
        """Set the state of a specific thread/node."""
        self._thread_states[node_name] = state
        logger.debug(f"Thread {node_name} state changed to: {state}")
