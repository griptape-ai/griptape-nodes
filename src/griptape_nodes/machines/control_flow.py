# Control flow machine
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.base_iterative_nodes import BaseIterativeStartNode
from griptape_nodes.exe_types.node_groups import SubflowNodeGroup
from griptape_nodes.exe_types.node_types import (
    LOCAL_EXECUTION,
    BaseNode,
    NodeResolutionState,
)
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
from griptape_nodes.retained_mode.managers.node_manager import NodeManager
from griptape_nodes.retained_mode.managers.settings import WorkflowExecutionMode

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow


@dataclass
class NextNodeInfo:
    """Information about the next node to execute and how to reach it."""

    node: BaseNode
    entry_parameter: Parameter | None


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
    end_node: BaseNode | None = None
    is_isolated: bool

    def __init__(
        self,
        flow_name: str,
        max_nodes_in_parallel: int,
        *,
        execution_type: WorkflowExecutionMode = WorkflowExecutionMode.SEQUENTIAL,
        pickle_control_flow_result: bool = False,
        is_isolated: bool = False,
    ) -> None:
        self.flow_name = flow_name
        if execution_type == WorkflowExecutionMode.PARALLEL:
            # Get the global DagBuilder from FlowManager
            from griptape_nodes.machines.dag_builder import DagBuilder
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            # Create isolated DagBuilder for independent subflows
            if is_isolated:
                dag_builder = DagBuilder()
                logger.debug("Created isolated DagBuilder for flow '%s'", flow_name)
            else:
                dag_builder = GriptapeNodes.FlowManager().global_dag_builder

            self.resolution_machine = ParallelResolutionMachine(
                flow_name, max_nodes_in_parallel, dag_builder=dag_builder
            )
        else:
            self.resolution_machine = SequentialResolutionMachine()
        self.current_nodes = []
        self.pickle_control_flow_result = pickle_control_flow_result
        self.is_isolated = is_isolated

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
                    GriptapeNodes.FlowManager()
                    .get_connections()
                    .get_connected_node(current_node, output_parameter, include_internal=False)
                )
                if node_connection is not None:
                    node, entry_parameter = node_connection
                    next_nodes.append(NextNodeInfo(node=node, entry_parameter=entry_parameter))
            # Get next control output for this node
            else:
                next_output = current_node.get_next_control_output()
                if next_output is not None:
                    if isinstance(current_node, BaseIterativeStartNode):
                        if current_node.end_node is None:
                            msg = "Iterative start node has no end node"
                            raise ValueError(msg)
                        next_nodes.append(NextNodeInfo(node=current_node.end_node, entry_parameter=None))
                        continue
                    node_connection = (
                        GriptapeNodes.FlowManager()
                        .get_connections()
                        .get_connected_node(current_node, next_output, include_internal=False)
                    )
                    if node_connection is not None:
                        node, entry_parameter = node_connection
                        next_nodes.append(NextNodeInfo(node=node, entry_parameter=entry_parameter))
                else:
                    logger.debug("Control Flow: Node '%s' has no control output", current_node.name)

        # If no connections found, check execution queue
        if not next_nodes and not self.is_isolated:
            node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
            if node is not None:
                next_nodes.append(NextNodeInfo(node=node, entry_parameter=None))

        return next_nodes

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
            if context.end_node == current_node:
                return CompleteState
            return NextNodeState
        return None


def _resolve_target_node_for_control_flow(next_node_info: NextNodeInfo) -> tuple[BaseNode, Parameter | None]:
    """Resolve the target node, replacing children with their parent node group if necessary.

    If the target node is inside a non-local node group, returns the parent node group instead.

    Args:
        next_node_info: Information about the next node to process

    Returns:
        Tuple of (resolved_node, entry_parameter)
    """
    target_node = next_node_info.node
    entry_parameter = next_node_info.entry_parameter

    # Check if node has a parent and if parent is not local execution
    if target_node.parent_group is not None and isinstance(target_node.parent_group, SubflowNodeGroup):
        parent_group = target_node.parent_group
        execution_env = parent_group.get_parameter_value(parent_group.execution_environment.name)
        if execution_env != LOCAL_EXECUTION:
            logger.info(
                "Control Flow: Redirecting from child node '%s' to parent node group '%s' (execution environment: %s)",
                target_node.name,
                parent_group.name,
                execution_env,
            )
            # Move to parent instead of child
            target_node = parent_group
            # Entry parameter should be None for the parent node group
            entry_parameter = None

    return target_node, entry_parameter


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
        # If a node has a parent (is in a node group), move to the parent instead
        next_nodes = []
        for next_node_info in next_node_infos:
            target_node, entry_parameter = _resolve_target_node_for_control_flow(next_node_info)
            target_node.set_entry_control_parameter(entry_parameter)
            next_nodes.append(target_node)

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
        context.end_node = None
        logger.info("Flow is complete.")
        return None

    @staticmethod
    async def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return None


# MACHINE TIME!!!
class ControlFlowMachine(FSM[ControlFlowContext]):
    def __init__(
        self,
        flow_name: str,
        *,
        pickle_control_flow_result: bool = False,
        is_isolated: bool = False,
    ) -> None:
        execution_type = GriptapeNodes.ConfigManager().get_config_value(
            "workflow_execution_mode", default=WorkflowExecutionMode.SEQUENTIAL
        )
        max_nodes_in_parallel = GriptapeNodes.ConfigManager().get_config_value("max_nodes_in_parallel", default=5)
        context = ControlFlowContext(
            flow_name,
            max_nodes_in_parallel,
            execution_type=execution_type,
            pickle_control_flow_result=pickle_control_flow_result,
            is_isolated=is_isolated,
        )
        super().__init__(context)

    async def start_flow(
        self, start_node: BaseNode, end_node: BaseNode | None = None, *, debug_mode: bool = False
    ) -> None:
        # If using DAG resolution, process data_nodes from queue first
        if isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            current_nodes = await self._process_nodes_for_dag(start_node)
        else:
            current_nodes = [start_node]
            if isinstance(start_node.parent_group, SubflowNodeGroup):
                # In sequential mode, we aren't going to run this. Just continue.
                node = GriptapeNodes.FlowManager().get_next_node_from_execution_queue()
                if node is not None:
                    await self.start_flow(node, end_node, debug_mode=debug_mode)
                    return
            # For control flow/sequential: emit all nodes in flow as involved
        self._context.current_nodes = current_nodes
        self._context.end_node = end_node
        # Set entry control parameter for initial node (None for workflow start)
        for node in current_nodes:
            node.set_entry_control_parameter(None)
        # Set up to debug
        self._context.paused = debug_mode
        flow_manager = GriptapeNodes.FlowManager()
        flow = flow_manager.get_flow_by_name(self._context.flow_name)
        if start_node != end_node:
            # This blocks all nodes in the entire flow from running. If we're just resolving one node, we don't want to block that.
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

    async def _process_nodes_for_dag(self, start_node: BaseNode) -> list[BaseNode]:  # noqa: C901, PLR0912
        """Process data_nodes from the global queue to build unified DAG.

        This method identifies data_nodes in the execution queue and processes
        their dependencies into the DAG resolution machine.

        For isolated subflows, this skips the global queue entirely and just
        processes the start node, as subflows are self-contained.
        """
        if not isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            return []

        # Use the DagBuilder from the resolution machine context (may be isolated or global)
        dag_builder = self._context.resolution_machine.context.dag_builder
        if dag_builder is None:
            msg = "DAG builder is not initialized."
            raise ValueError(msg)

        # Build with the first node (it should already be the proxy if it's part of a group)
        dag_builder.add_node_with_dependencies(start_node, start_node.name)

        # Check if we're using an isolated DagBuilder (for subflows)
        flow_manager = GriptapeNodes.FlowManager()
        node_manager = GriptapeNodes.NodeManager()
        is_isolated = dag_builder is not flow_manager.global_dag_builder

        if is_isolated:
            # For isolated subflows, we don't process the global queue
            # Just return the start node - the subflow is self-contained
            logger.debug(
                "Using isolated DagBuilder for flow '%s' - skipping global queue processing", self._context.flow_name
            )
            return [start_node]

        # For main flows using the global DagBuilder, process the global queue
        start_nodes = [start_node]
        from griptape_nodes.retained_mode.managers.flow_manager import DagExecutionType

        # PASS 1: Process all control/start nodes first to build control flow graphs
        queue_items = list(flow_manager.global_flow_queue.queue)
        for item in queue_items:
            if item.dag_execution_type in (DagExecutionType.CONTROL_NODE, DagExecutionType.START_NODE):
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                # Use proxy node if this node is part of a group, otherwise use original node
                node_to_add = node

                # Only add if not already added (proxy might already be in DAG)
                if node_to_add.name not in dag_builder.node_to_reference:
                    dag_builder.add_node_with_dependencies(node_to_add, node_to_add.name)
                    if node_to_add not in start_nodes:
                        start_nodes.append(node_to_add)
                flow_manager.global_flow_queue.queue.remove(item)

        # PASS 2: Process all data nodes after control graphs are built
        queue_items = list(flow_manager.global_flow_queue.queue)
        for item in queue_items:
            if item.dag_execution_type == DagExecutionType.DATA_NODE:
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                # Use proxy node if this node is part of a group, otherwise use original node
                node_to_add = node
                # Only add if not already added (proxy might already be in DAG)
                disconnected = True
                if node_to_add.name not in dag_builder.node_to_reference:
                    # Now, we need to create the DAG, but it can't be queued or used until it's dependencies have been resolved.
                    # Figure out which graph the data node belongs to, if it belongs to a graph.
                    for graph_start_node_name in dag_builder.graphs:
                        graph_start_node = node_manager.get_node_by_name(graph_start_node_name)
                        # Get boundary nodes (empty list if not connected)
                        boundary_nodes = flow_manager.is_node_connected(graph_start_node, node)
                        # This means this node is in the downstream connection of one of this graph.
                        if boundary_nodes:
                            # Is the node connected to a graph?
                            disconnected = False
                            if node.name not in dag_builder.start_node_candidates:
                                dag_builder.start_node_candidates[node.name] = {}
                            dag_builder.start_node_candidates[node.name][graph_start_node_name] = set(boundary_nodes)
                    if disconnected:
                        # If the node is not connected to any graph, we can add it as it's own graph here.
                        # It will not cause any overlapping confusion with existing graphs.
                        dag_builder.add_node_with_dependencies(node_to_add, node_to_add.name)
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
