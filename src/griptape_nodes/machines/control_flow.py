# Control flow machine
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import Parameter, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import CONTROL_INPUT_PARAMETER, LOCAL_EXECUTION, BaseNode, NodeResolutionState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.parallel_resolution import ExecuteDagState, ParallelResolutionMachine
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

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_types import NodeGroup


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
    node_to_proxy_map: dict[BaseNode, BaseNode]
    end_node: BaseNode | None = None

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
        self.node_to_proxy_map = {}

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
            if context.end_node == current_node:
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
        context.end_node = None
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

    async def start_flow(
        self, start_node: BaseNode, end_node: BaseNode | None = None, *, debug_mode: bool = False
    ) -> None:
        # FIRST: Scan all nodes in the flow and create node groups BEFORE any resolution
        flow_manager = GriptapeNodes.FlowManager()
        flow = flow_manager.get_flow_by_name(self._context.flow_name)
        logger.debug("Scanning flow '%s' for node groups before execution", self._context.flow_name)

        try:
            node_to_proxy_map = self._identify_and_create_node_group_proxies(flow, flow_manager.get_connections())
            if node_to_proxy_map:
                logger.info(
                    "Created %d proxy nodes for %d grouped nodes in flow '%s'",
                    len(set(node_to_proxy_map.values())),
                    len(node_to_proxy_map),
                    self._context.flow_name,
                )
            # Store the mapping in context so it can be used by resolution machines
            self._context.node_to_proxy_map = node_to_proxy_map
        except ValueError as e:
            logger.error("Failed to process node groups: %s", e)
            raise

        # Determine the actual start node (use proxy if it's part of a group)
        actual_start_node = node_to_proxy_map.get(start_node, start_node)

        # If using DAG resolution, process data_nodes from queue first
        if isinstance(self._context.resolution_machine, ParallelResolutionMachine):
            current_nodes = await self._process_nodes_for_dag(actual_start_node)
        else:
            current_nodes = [actual_start_node]
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

    async def _process_nodes_for_dag(self, start_node: BaseNode) -> list[BaseNode]:  # noqa: C901
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

        # Use the node-to-proxy map that was created in start_flow
        node_to_proxy_map = self._context.node_to_proxy_map

        # Build with the first node (it should already be the proxy if it's part of a group)
        dag_builder.add_node_with_dependencies(start_node, start_node.name)
        queue_items = list(flow_manager.global_flow_queue.queue)
        start_nodes = [start_node]
        # Find data_nodes and remove them from queue
        for item in queue_items:
            from griptape_nodes.retained_mode.managers.flow_manager import DagExecutionType

            if item.dag_execution_type in (DagExecutionType.CONTROL_NODE, DagExecutionType.START_NODE):
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                # Use proxy node if this node is part of a group, otherwise use original node
                if node in node_to_proxy_map:
                    node_to_add = node_to_proxy_map[node]
                else:
                    node_to_add = node
                # Only add if not already added (proxy might already be in DAG)
                if node_to_add.name not in dag_builder.node_to_reference:
                    dag_builder.add_node_with_dependencies(node_to_add, node_to_add.name)
                    if node_to_add not in start_nodes:
                        start_nodes.append(node_to_add)
                flow_manager.global_flow_queue.queue.remove(item)
            elif item.dag_execution_type == DagExecutionType.DATA_NODE:
                node = item.node
                node.state = NodeResolutionState.UNRESOLVED
                # Use proxy node if this node is part of a group, otherwise use original node
                if node in node_to_proxy_map:
                    node_to_add = node_to_proxy_map[node]
                else:
                    node_to_add = node
                # Only add if not already added (proxy might already be in DAG)
                if node_to_add.name not in dag_builder.node_to_reference:
                    dag_builder.add_node_with_dependencies(node_to_add, node_to_add.name)
                flow_manager.global_flow_queue.queue.remove(item)

        return start_nodes

    def _identify_and_create_node_group_proxies(
        self, flow: ControlFlow, connections: Connections
    ) -> dict[BaseNode, BaseNode]:
        """Scan all nodes in flow, identify groups, and create proxy nodes.

        Returns:
            Dictionary mapping original nodes to their proxy nodes (only for grouped nodes)
        """
        from griptape_nodes.exe_types.node_types import NodeGroup, NodeGroupProxyNode

        # Step 1: Identify groups by scanning all nodes in the flow
        groups: dict[str, NodeGroup] = {}
        for node in flow.nodes.values():
            group_id = node.get_parameter_value("job_group")

            # Skip nodes without group assignment, empty group ID, or locked nodes
            if not group_id or group_id == "" or node.lock:
                continue

            # Create group if it doesn't exist
            if group_id not in groups:
                groups[group_id] = NodeGroup(group_id=group_id)

            # Add node to group
            groups[group_id].add_node(node)

        if not groups:
            return {}

        # Step 2: Analyze connections for each group
        for group in groups.values():
            self._analyze_group_connections(group, connections)

        # Step 3: Validate each group
        for group in groups.values():
            group.validate_no_intermediate_nodes(connections.connections)

        # Step 4: Create proxy nodes and build mapping
        node_to_proxy_map: dict[BaseNode, BaseNode] = {}
        for group_id, group in groups.items():
            # Create proxy node
            proxy_name = f"__group_proxy_{group_id}"
            proxy_node = NodeGroupProxyNode(name=proxy_name, node_group=group)

            # Register the proxy node with ObjectManager so it can be found during parameter updates
            obj_manager = GriptapeNodes.ObjectManager()
            obj_manager.add_object_by_name(proxy_name, proxy_node)

            # Map all grouped nodes to this proxy
            for node in group.nodes.values():
                node_to_proxy_map[node] = proxy_node

            # Remap connections to point to proxy
            self._remap_connections_to_proxy_node(group, proxy_node, connections)

            # Now create proxy parameters (after remapping so original references are saved)
            proxy_node.create_proxy_parameters()

        return node_to_proxy_map

    def _analyze_group_connections(self, group: NodeGroup, connections: Connections) -> None:
        """Analyze and categorize connections for a node group."""
        node_names_in_group = group.nodes.keys()

        # Analyze all connections in the flow
        for conn in connections.connections.values():
            source_in_group = conn.source_node.name in node_names_in_group
            target_in_group = conn.target_node.name in node_names_in_group

            if source_in_group and target_in_group:
                # Both endpoints in group - internal connection
                group.internal_connections.append(conn)
            elif source_in_group and not target_in_group:
                # From group to outside - external outgoing
                group.external_outgoing_connections.append(conn)
            elif not source_in_group and target_in_group:
                # From outside to group - external incoming
                group.external_incoming_connections.append(conn)

    def _remap_connections_to_proxy_node(
        self, group: NodeGroup, proxy_node: BaseNode, connections: Connections
    ) -> None:
        """Remap external connections from group nodes to the proxy node."""
        # Remap external incoming connections (from outside -> group becomes outside -> proxy)
        for conn in group.external_incoming_connections:
            conn_id = id(conn)

            # Save original target node before remapping (for cleanup later)
            original_target_node = conn.target_node
            group.original_incoming_targets[conn_id] = original_target_node

            # Remove old incoming index entry
            if (
                conn.target_node.name in connections.incoming_index
                and conn.target_parameter.name in connections.incoming_index[conn.target_node.name]
            ):
                connections.incoming_index[conn.target_node.name][conn.target_parameter.name].remove(conn_id)

            # Update connection target to proxy
            conn.target_node = proxy_node

            # Create proxy parameter name using original node name
            sanitized_node_name = original_target_node.name.replace(" ", "_")
            proxy_param_name = f"{sanitized_node_name}__{conn.target_parameter.name}"

            # Add new incoming index entry with proxy parameter name
            connections.incoming_index.setdefault(proxy_node.name, {}).setdefault(proxy_param_name, []).append(conn_id)

        # Remap external outgoing connections (group -> outside becomes proxy -> outside)
        for conn in group.external_outgoing_connections:
            conn_id = id(conn)

            # Save original source node before remapping (for cleanup later)
            original_source_node = conn.source_node
            group.original_outgoing_sources[conn_id] = original_source_node

            # Remove old outgoing index entry
            if (
                conn.source_node.name in connections.outgoing_index
                and conn.source_parameter.name in connections.outgoing_index[conn.source_node.name]
            ):
                connections.outgoing_index[conn.source_node.name][conn.source_parameter.name].remove(conn_id)

            # Update connection source to proxy
            conn.source_node = proxy_node

            # Create proxy parameter name using original node name
            sanitized_node_name = original_source_node.name.replace(" ", "_")
            proxy_param_name = f"{sanitized_node_name}__{conn.source_parameter.name}"

            # Add new outgoing index entry with proxy parameter name
            connections.outgoing_index.setdefault(proxy_node.name, {}).setdefault(proxy_param_name, []).append(conn_id)

    async def cancel_flow(self) -> None:
        """Cancel all nodes in the flow by delegating to the resolution machine."""
        await self.resolution_machine.cancel_all_nodes()

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None

    def cleanup_proxy_nodes(self) -> None:
        """Cleanup all proxy nodes and restore original connections."""
        if not self._context.node_to_proxy_map:
            # If we're calling cleanup, but it's already been cleaned up, we just want to return.
            return

        # Get all unique proxy nodes
        proxy_nodes = set(self._context.node_to_proxy_map.values())

        # Cleanup each proxy node using the existing method
        for proxy_node in proxy_nodes:
            ExecuteDagState._cleanup_proxy_node(proxy_node)

        # Clear the proxy mapping
        self._context.node_to_proxy_map.clear()

    @property
    def resolution_machine(self) -> ParallelResolutionMachine | SequentialResolutionMachine:
        return self._context.resolution_machine
