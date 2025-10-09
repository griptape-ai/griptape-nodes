# Control flow machine
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import Parameter, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import CONTROL_INPUT_PARAMETER, LOCAL_EXECUTION, BaseNode, NodeResolutionState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine
from griptape_nodes.machines.sequential_resolution import SequentialResolutionMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowResolvedEvent,
    CurrentControlNodeEvent,
    InvolvedNodesEvent,
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
    current_nodes: list[BaseNode]
    resolution_machine: ParallelResolutionMachine | SequentialResolutionMachine
    selected_output: Parameter | None
    paused: bool = False
    flow_name: str
    pickle_control_flow_result: bool

    def __init__(
        self,
        flow_name: str,
        max_nodes_in_parallel: int,
        *,
        execution_type: WorkflowExecutionMode = WorkflowExecutionMode.SEQUENTIAL,
        pickle_control_flow_result: bool = False,
    ) -> None:
        self.flow_name = flow_name
        if execution_type == WorkflowExecutionMode.PARALLEL:
            # Get the global DagBuilder from FlowManager
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            dag_builder = GriptapeNodes.FlowManager().global_dag_builder
            self.resolution_machine = ParallelResolutionMachine(
                flow_name, max_nodes_in_parallel, dag_builder=dag_builder
            )
        else:
            self.resolution_machine = SequentialResolutionMachine()
        self.current_nodes = []
        self.pickle_control_flow_result = pickle_control_flow_result

    def get_next_nodes(self, output_parameter: Parameter | None = None) -> list[NextNodeInfo]:
        """Get all next nodes from the current nodes.

        Returns:
            list[NextNodeInfo]: List of next nodes to process
        """
        next_nodes = []
        for current_node in self.current_nodes:
            if output_parameter is not None:
                # Get connected node from control flow
                node_connection = (
                    GriptapeNodes.FlowManager().get_connections().get_connected_node(current_node, output_parameter)
                )
                if node_connection is not None:
                    node, entry_parameter = node_connection
                    next_nodes.append(NextNodeInfo(node=node, entry_parameter=entry_parameter))
            else:
                # Get next control output for this node
                if current_node.get_parameter_value(current_node.execution_environment.name) != LOCAL_EXECUTION:
                    next_output = self.get_next_control_output_for_non_local_execution(current_node)
                else:
                    next_output = current_node.get_next_control_output()
                if next_output is not None:
                    node_connection = (
                        GriptapeNodes.FlowManager().get_connections().get_connected_node(current_node, next_output)
                    )
                    if node_connection is not None:
                        node, entry_parameter = node_connection
                        next_nodes.append(NextNodeInfo(node=node, entry_parameter=entry_parameter))
                else:
                    logger.debug("Control Flow: Node '%s' has no control output", current_node.name)

        # If no connections found, check execution queue
        if not next_nodes:
            node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if node is not None:
                next_nodes.append(NextNodeInfo(node=node, entry_parameter=None))

        return next_nodes

    # Mirrored in @parallel_resolution.py. if you update one, update the other.
    def get_next_control_output_for_non_local_execution(self, node: BaseNode) -> Parameter | None:
        for param_name, value in node.parameter_output_values.items():
            parameter = node.get_parameter_by_name(param_name)
            if (
                parameter is not None
                and parameter.type == ParameterTypeBuiltin.CONTROL_TYPE
                and value == CONTROL_INPUT_PARAMETER
            ):
                # This is the parameter
                logger.debug("Control Flow: Found control output parameter '%s' for non-local execution", param_name)
                return parameter
        return None

    def reset(self, *, cancel: bool = False) -> None:
        if self.current_nodes is not None:
            for node in self.current_nodes:
                node.clear_node()
        self.current_nodes = []
        self.resolution_machine.reset_machine(cancel=cancel)
        self.selected_output = None
        self.paused = False


# GOOD!
class ResolveNodeState(State):
    @staticmethod
    async def on_enter(context: ControlFlowContext) -> type[State] | None:
        # The state machine has started, but it hasn't began to execute yet.
        if len(context.current_nodes) == 0:
            # We don't have anything else to do. Move back to Complete State so it has to restart.
            return CompleteState

        # Mark all current nodes unresolved and broadcast events
        for current_node in context.current_nodes:
            if not current_node.lock:
                current_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                    )
                )
            # Now broadcast that we have a current control node.
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=CurrentControlNodeEvent(node_name=current_node.name))
                )
            )
            logger.info("Resolving %s", current_node.name)
        if not context.paused:
            # Call the update. Otherwise wait
            return ResolveNodeState
        return None

    # This is necessary to transition to the next step.
    @staticmethod
    async def on_update(context: ControlFlowContext) -> type[State] | None:
        # If no current nodes, we're done
        if len(context.current_nodes) == 0:
            return CompleteState

        # Resolve nodes - pass first node for sequential resolution
        current_node = context.current_nodes[0] if context.current_nodes else None
        await context.resolution_machine.resolve_node(current_node)

        if context.resolution_machine.is_complete():
            # Get the last resolved node from the DAG and set it as current
            if isinstance(context.resolution_machine, ParallelResolutionMachine):
                last_resolved_node = context.resolution_machine.get_last_resolved_node()
                if last_resolved_node:
                    context.current_nodes = [last_resolved_node]
                return CompleteState
            return NextNodeState
        return None


class NextNodeState(State):
    @staticmethod
    async def on_enter(context: ControlFlowContext) -> type[State] | None:
        if len(context.current_nodes) == 0:
            return CompleteState

        # Check for stop_flow on any current nodes
        for current_node in context.current_nodes[:]:
            if current_node.stop_flow:
                current_node.stop_flow = False
                context.current_nodes.remove(current_node)

        # If all nodes stopped flow, complete
        if len(context.current_nodes) == 0:
            return CompleteState

        # Get all next nodes from current nodes
        next_node_infos = context.get_next_nodes()

        # Broadcast selected control output events for nodes with outputs
        for current_node in context.current_nodes:
            next_output = current_node.get_next_control_output()
            if next_output is not None:
                context.selected_output = next_output
                GriptapeNodes.EventManager().put_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=SelectedControlOutputEvent(
                                node_name=current_node.name,
                                selected_output_parameter_name=next_output.name,
                            )
                        )
                    )
                )

        # If no next nodes, we're complete
        if not next_node_infos:
            return CompleteState

        # Set up next nodes as current nodes
        next_nodes = []
        for next_node_info in next_node_infos:
            next_node_info.node.set_entry_control_parameter(next_node_info.entry_parameter)
            next_nodes.append(next_node_info.node)

        context.current_nodes = next_nodes
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
        # Broadcast completion events for any remaining current nodes
        for current_node in context.current_nodes:
            # Use pickle-based serialization for complex parameter output values
            from griptape_nodes.retained_mode.managers.node_manager import NodeManager

            parameter_output_values, unique_uuid_to_values = NodeManager.serialize_parameter_output_values(
                current_node, use_pickling=context.pickle_control_flow_result
            )
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=ControlFlowResolvedEvent(
                            end_node_name=current_node.name,
                            parameter_output_values=parameter_output_values,
                            unique_parameter_uuid_to_values=unique_uuid_to_values if unique_uuid_to_values else None,
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
    def __init__(self, flow_name: str, *, pickle_control_flow_result: bool = False) -> None:
        execution_type = GriptapeNodes.ConfigManager().get_config_value(
            "workflow_execution_mode", default=WorkflowExecutionMode.SEQUENTIAL
        )
        max_nodes_in_parallel = GriptapeNodes.ConfigManager().get_config_value("max_nodes_in_parallel", default=5)
        context = ControlFlowContext(
            flow_name,
            max_nodes_in_parallel,
            execution_type=execution_type,
            pickle_control_flow_result=pickle_control_flow_result,
        )
        super().__init__(context)

    async def start_flow(self, start_node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        # If using DAG resolution, process data_nodes from queue first
        if isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            current_nodes = await self._process_nodes_for_dag(start_node)
        else:
            current_nodes = [start_node]
            # For control flow/sequential: emit all nodes in flow as involved
        self._context.current_nodes = current_nodes
        # Set entry control parameter for initial node (None for workflow start)
        for node in current_nodes:
            node.set_entry_control_parameter(None)
        # Set up to debug
        self._context.paused = debug_mode
        flow_manager = GriptapeNodes.FlowManager()
        flow = flow_manager.get_flow_by_name(self._context.flow_name)
        involved_nodes = list(flow.nodes.keys())
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=involved_nodes))
            )
        )
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

    async def _process_nodes_for_dag(self, start_node: BaseNode) -> list[BaseNode]:
        """Process data_nodes from the global queue to build unified DAG.

        This method identifies data_nodes in the execution queue and processes
        their dependencies into the DAG resolution machine.
        """
        if not isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            return []
        # Get the global flow queue
        flow_manager = GriptapeNodes.FlowManager()
        dag_builder = flow_manager.global_dag_builder
        if dag_builder is None:
            msg = "DAG builder is not initialized."
            raise ValueError(msg)
        # Build with the first node:
        dag_builder.add_node_with_dependencies(start_node, start_node.name)
        queue_items = list(flow_manager.global_flow_queue.queue)
        start_nodes = [start_node]
        # Find data_nodes and remove them from queue
        for item in queue_items:
            from griptape_nodes.retained_mode.managers.flow_manager import DagExecutionType

            if item.dag_execution_type in (DagExecutionType.CONTROL_NODE, DagExecutionType.START_NODE):
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                dag_builder.add_node_with_dependencies(node, node.name)
                flow_manager.global_flow_queue.queue.remove(item)
                start_nodes.append(node)
            elif item.dag_execution_type == DagExecutionType.DATA_NODE:
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                # Build here.
                dag_builder.add_node_with_dependencies(node, node.name)
                flow_manager.global_flow_queue.queue.remove(item)
        return start_nodes

    async def cancel_flow(self) -> None:
        """Cancel all nodes in the flow by delegating to the resolution machine."""
        await self.resolution_machine.cancel_all_nodes()

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None

    @property
    def resolution_machine(self) -> ParallelResolutionMachine | SequentialResolutionMachine:
        return self._context.resolution_machine
