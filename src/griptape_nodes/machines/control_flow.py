# Control flow machine
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine
from griptape_nodes.machines.sequential_resolution import SequentialResolutionMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowResolvedEvent,
    CurrentControlNodeEvent,
    SelectedControlOutputEvent,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.settings import WorkflowExecutionMode


@dataclass
class NextNodeInfo:
    """Information about the next node to execute and how to reach it."""

    node: BaseNode
    entry_parameter: Parameter | None


if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow

logger = logging.getLogger("griptape_nodes")


# This is the control flow context. Owns the Resolution Machine
class ControlFlowContext:
    flow: ControlFlow
    current_node: BaseNode | None
    resolution_machine: ParallelResolutionMachine | SequentialResolutionMachine
    selected_output: Parameter | None
    paused: bool = False
    flow_name: str

    def __init__(
        self,
        flow_name: str,
        max_nodes_in_parallel: int,
        *,
        execution_type: WorkflowExecutionMode = WorkflowExecutionMode.SEQUENTIAL,
    ) -> None:
        self.flow_name = flow_name
        if execution_type == WorkflowExecutionMode.PARALLEL:
            self.resolution_machine = ParallelResolutionMachine(flow_name, max_nodes_in_parallel)
        else:
            self.resolution_machine = SequentialResolutionMachine()
        self.current_node = None

    def get_next_node(self, output_parameter: Parameter) -> NextNodeInfo | None:
        """Get the next node and the target parameter that will receive the control flow.

        Returns:
            NextNodeInfo | None: Information about the next node or None if no connection
        """
        if self.current_node is not None:
            node_connection = (
                GriptapeNodes.FlowManager().get_connections().get_connected_node(self.current_node, output_parameter)
            )
            if node_connection is not None:
                node, entry_parameter = node_connection
                return NextNodeInfo(node=node, entry_parameter=entry_parameter)
            # Continue Execution to the next node that needs to be executed using global execution queue
            # Get the next node in the execution queue, or None if queue is empty
            node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if node is not None:
                return NextNodeInfo(node=node, entry_parameter=None)
        return None

    def reset(self, *, cancel: bool = False) -> None:
        if self.current_node:
            self.current_node.clear_node()
        self.current_node = None
        self.resolution_machine.reset_machine(cancel=cancel)
        self.selected_output = None
        self.paused = False


# GOOD!
class ResolveNodeState(State):
    @staticmethod
    async def on_enter(context: ControlFlowContext) -> type[State] | None:
        # The state machine has started, but it hasn't began to execute yet.
        if context.current_node is None:
            # We don't have anything else to do. Move back to Complete State so it has to restart.
            return CompleteState

        # Mark the node unresolved, and broadcast an event to the GUI.
        if not context.current_node.lock:
            context.current_node.make_node_unresolved(
                current_states_to_trigger_change_event=set(
                    {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                )
            )
        # Now broadcast that we have a current control node.
        GriptapeNodes.EventManager().put_event(
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
    async def on_update(context: ControlFlowContext) -> type[State] | None:
        # If node has not already been resolved!
        if context.current_node is None:
            return CompleteState
        if context.current_node.state != NodeResolutionState.RESOLVED:
            await context.resolution_machine.resolve_node(context.current_node)

        if context.resolution_machine.is_complete():
            return NextNodeState
        return None


class NextNodeState(State):
    @staticmethod
    async def on_enter(context: ControlFlowContext) -> type[State] | None:
        if context.current_node is None:
            return CompleteState
        # I did define this on the ControlNode.
        if context.current_node.stop_flow:
            # We're done here.
            context.current_node.stop_flow = False
            return CompleteState
        next_output = context.current_node.get_next_control_output()
        next_node_info = None

        if next_output is not None:
            context.selected_output = next_output
            next_node_info = context.get_next_node(context.selected_output)
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=SelectedControlOutputEvent(
                            node_name=context.current_node.name,
                            selected_output_parameter_name=next_output.name,
                        )
                    )
                )
            )
        else:
            # Get the next node in the execution queue, or None if queue is empty
            next_node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if next_node is not None:
                next_node_info = NextNodeInfo(node=next_node, entry_parameter=None)

        # The parameter that will be evaluated next
        if next_node_info is None:
            # If no node attached
            return CompleteState

        # Always set the entry control parameter (None for execution queue nodes)
        next_node_info.node.set_entry_control_parameter(next_node_info.entry_parameter)

        context.current_node = next_node_info.node
        context.selected_output = None
        if not context.paused:
            return ResolveNodeState
        return None

    @staticmethod
    async def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return ResolveNodeState


class CompleteState(State):
    @staticmethod
    async def on_enter(context: ControlFlowContext) -> type[State] | None:
        if context.current_node is not None:
            GriptapeNodes.EventManager().put_event(
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
    async def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return None


# MACHINE TIME!!!
class ControlFlowMachine(FSM[ControlFlowContext]):
    def __init__(self, flow_name: str) -> None:
        execution_type = GriptapeNodes.ConfigManager().get_config_value(
            "workflow_execution_mode", default=WorkflowExecutionMode.SEQUENTIAL
        )
        max_nodes_in_parallel = GriptapeNodes.ConfigManager().get_config_value("max_nodes_in_parallel", default=5)
        context = ControlFlowContext(flow_name, max_nodes_in_parallel, execution_type=execution_type)
        super().__init__(context)

    async def start_flow(self, start_node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        # If using DAG resolution, process data_nodes from queue first
        if isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            await self._process_data_nodes_for_dag()
        self._context.current_node = start_node
        # Set entry control parameter for initial node (None for workflow start)
        start_node.set_entry_control_parameter(None)
        # Set up to debug
        self._context.paused = debug_mode
        await self.start(ResolveNodeState)  # Begins the flow

    async def update(self) -> None:
        if self._current_state is None:
            msg = "Attempted to run the next step of a workflow that was either already complete or has not started."
            raise RuntimeError(msg)
        await super().update()

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode
        self._context.resolution_machine.change_debug_mode(debug_mode=debug_mode)

    async def granular_step(self, change_debug_mode: bool) -> None:  # noqa: FBT001
        resolution_machine = self._context.resolution_machine

        if change_debug_mode:
            resolution_machine.change_debug_mode(debug_mode=True)
        await resolution_machine.update()

        # Tick the control flow if the current machine isn't busy
        if self._current_state is ResolveNodeState and (  # noqa: SIM102
            resolution_machine.is_complete() or not resolution_machine.is_started()
        ):
            # Don't tick ourselves if we are already complete.
            if self._current_state is not None:
                await self.update()

    async def node_step(self) -> None:
        resolution_machine = self._context.resolution_machine

        resolution_machine.change_debug_mode(debug_mode=False)

        # If we're in the resolution phase, step the resolution machine
        if self._current_state is ResolveNodeState:
            await resolution_machine.update()

        # Tick the control flow if the current machine isn't busy
        if self._current_state is ResolveNodeState and (
            resolution_machine.is_complete() or not resolution_machine.is_started()
        ):
            await self.update()

    async def _process_data_nodes_for_dag(self) -> None:
        """Process data_nodes from the global queue to build unified DAG.

        This method identifies data_nodes in the execution queue and processes
        their dependencies into the DAG resolution machine.
        """
        if not isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            return
        # Get the global flow queue
        flow_manager = GriptapeNodes.FlowManager()
        queue_items = list(flow_manager.global_flow_queue.queue)

        # Find data_nodes and remove them from queue
        data_nodes = []
        for item in queue_items:
            from griptape_nodes.retained_mode.managers.flow_manager import DagExecutionType

            if item.dag_execution_type == DagExecutionType.DATA_NODE:
                data_nodes.append(item.node)
                flow_manager.global_flow_queue.queue.remove(item)

        # Build DAG for each data node
        for node in data_nodes:
            node.state = NodeResolutionState.UNRESOLVED
            await self._context.resolution_machine.resolve_node(node, build_only=True)

            # Run resolution until complete for this node's subgraph
            while not self._context.resolution_machine.is_complete():
                await self._context.resolution_machine.update()

            # Reset the machine state to allow adding more nodes
            self._context.resolution_machine.current_state = None

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None

    @property
    def resolution_machine(self) -> ParallelResolutionMachine | SequentialResolutionMachine:
        return self._context.resolution_machine
