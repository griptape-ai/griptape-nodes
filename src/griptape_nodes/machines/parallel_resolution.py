from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.connections import Direction
from griptape_nodes.exe_types.core_types import Parameter, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import (
    CONTROL_INPUT_PARAMETER,
    LOCAL_EXECUTION,
    BaseNode,
    NodeGroupProxyNode,
    NodeResolutionState,
)
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.dag_builder import NodeState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentControlNodeEvent,
    CurrentDataNodeEvent,
    InvolvedNodesEvent,
    NodeResolvedEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
    SetParameterValueResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.common.directed_graph import DirectedGraph
    from griptape_nodes.machines.dag_builder import DagBuilder, DagNode
    from griptape_nodes.retained_mode.managers.flow_manager import FlowManager

logger = logging.getLogger("griptape_nodes")


class WorkflowState(StrEnum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"
    CANCELED = "canceled"


class ParallelResolutionContext:
    paused: bool
    flow_name: str
    error_message: str | None
    workflow_state: WorkflowState
    # Execution fields
    async_semaphore: asyncio.Semaphore
    task_to_node: dict[asyncio.Task, DagNode]
    dag_builder: DagBuilder | None
    last_resolved_node: BaseNode | None  # Track the last node that was resolved
    last_resolved_node: BaseNode | None  # Track the last node that was resolved

    def __init__(
        self, flow_name: str, max_nodes_in_parallel: int | None = None, dag_builder: DagBuilder | None = None
    ) -> None:
        self.flow_name = flow_name
        self.paused = False
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR
        self.dag_builder = dag_builder
        self.last_resolved_node = None
        self.last_resolved_node = None

        # Initialize execution fields
        max_nodes_in_parallel = max_nodes_in_parallel if max_nodes_in_parallel is not None else 5
        self.async_semaphore = asyncio.Semaphore(max_nodes_in_parallel)
        self.task_to_node = {}

    @property
    def node_to_reference(self) -> dict[str, DagNode]:
        """Get node_to_reference from dag_builder if available."""
        if not self.dag_builder:
            msg = "DagBuilder is not initialized"
            raise ValueError(msg)
        return self.dag_builder.node_to_reference

    @property
    def networks(self) -> dict[str, DirectedGraph]:
        """Get node_to_reference from dag_builder if available."""
        if not self.dag_builder:
            msg = "DagBuilder is not initialized"
            raise ValueError(msg)
        return self.dag_builder.graphs

    def reset(self, *, cancel: bool = False) -> None:
        self.paused = False
        if cancel:
            self.workflow_state = WorkflowState.CANCELED
            # Only access node_to_reference if dag_builder exists
            if self.dag_builder:
                for node in self.node_to_reference.values():
                    node.node_state = NodeState.CANCELED
        else:
            self.workflow_state = WorkflowState.NO_ERROR
            self.error_message = None
            self.task_to_node.clear()
            self.last_resolved_node = None
            self.last_resolved_node = None

        # Clear DAG builder state to allow re-adding nodes on subsequent runs
        if self.dag_builder:
            self.dag_builder.clear()


class ExecuteDagState(State):
    @staticmethod
    async def handle_done_nodes(context: ParallelResolutionContext, done_node: DagNode, network_name: str) -> None:
        current_node = done_node.node_reference

        # Check if node was already resolved (shouldn't happen)
        if current_node.state == NodeResolutionState.RESOLVED and not current_node.lock:
            logger.error(
                "DUPLICATE COMPLETION DETECTED: Node '%s' was already RESOLVED but handle_done_nodes was called again from network '%s'. This should not happen!",
                current_node.name,
                network_name,
            )
            return

        # Check if this is a NodeGroupProxyNode - if so, handle grouped nodes

        if isinstance(current_node, NodeGroupProxyNode):
            await ExecuteDagState._handle_group_proxy_completion(context, current_node, network_name)
            return
        # Publish all parameter updates.
        current_node.state = NodeResolutionState.RESOLVED
        # Track this as the last resolved node
        context.last_resolved_node = current_node
        # Track this as the last resolved node
        context.last_resolved_node = current_node
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

            await GriptapeNodes.EventManager().aput_event(
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

        await GriptapeNodes.EventManager().aput_event(
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
        # Now the final thing to do, is to take their directed graph and update it.
        ExecuteDagState.get_next_control_graph(context, current_node, network_name)

    # Method is mirrored in Control_flow.py. If you update one, update the other.
    @staticmethod
    async def _handle_group_proxy_completion(
        context: ParallelResolutionContext, proxy_node: BaseNode, network_name: str
    ) -> None:
        """Handle completion of a NodeGroupProxyNode by marking all grouped nodes as resolved.

        When a NodeGroupProxyNode completes, all nodes in the group have been executed
        in parallel by the NodeExecutor. This method marks each grouped node as RESOLVED
        and emits NodeResolvedEvent for each one.

        Args:
            proxy_node: The NodeGroupProxyNode that completed execution
            context: The ParallelResolutionContext
            network_name: The name of the network
        """
        from griptape_nodes.exe_types.node_types import NodeGroupProxyNode

        if not isinstance(proxy_node, NodeGroupProxyNode):
            return

        node_group = proxy_node.node_group_data

        # Mark all grouped nodes as resolved and emit events
        proxy_node.state = NodeResolutionState.RESOLVED
        for grouped_node in node_group.nodes.values():
            # Mark node as resolved
            grouped_node.state = NodeResolutionState.RESOLVED

            # Emit parameter update events for each output parameter
            for parameter_name, value in grouped_node.parameter_output_values.items():
                parameter = grouped_node.get_parameter_by_name(parameter_name)
                if parameter is None:
                    logger.warning(
                        "Node '%s' in group '%s' has output parameter '%s' but parameter not found",
                        grouped_node.name,
                        node_group.group_id,
                        parameter_name,
                    )
                    continue

                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value

                await GriptapeNodes.EventManager().aput_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=grouped_node.name,
                                parameter_name=parameter_name,
                                data_type=data_type,
                                value=TypeValidator.safe_serialize(value),
                            )
                        ),
                    )
                )

            # Emit NodeResolvedEvent for the grouped node
            library = LibraryRegistry.get_libraries_with_node_type(grouped_node.__class__.__name__)
            library_name = library[0] if len(library) == 1 else None

            await GriptapeNodes.EventManager().aput_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=NodeResolvedEvent(
                            node_name=grouped_node.name,
                            parameter_output_values=TypeValidator.safe_serialize(grouped_node.parameter_output_values),
                            node_type=grouped_node.__class__.__name__,
                            specific_library_name=library_name,
                        )
                    )
                )
            )

        # Cleanup: restore connections and deregister proxy
        ExecuteDagState.get_next_control_graph(context, proxy_node, network_name)
        ExecuteDagState._cleanup_proxy_node(proxy_node)

    @staticmethod
    def _cleanup_proxy_node(proxy_node: BaseNode) -> None:
        """Clean up a NodeGroupProxyNode after execution completes.

        Restores original connections from proxy back to grouped nodes and
        deregisters the proxy node from ObjectManager.

        Args:
            proxy_node: The NodeGroupProxyNode to clean up
        """
        from griptape_nodes.exe_types.node_types import NodeGroupProxyNode

        if not isinstance(proxy_node, NodeGroupProxyNode):
            return

        node_group = proxy_node.node_group_data
        connections = GriptapeNodes.FlowManager().get_connections()

        # Restore external incoming connections (proxy -> original target node)
        for conn in node_group.external_incoming_connections:
            conn_id = id(conn)

            # Get original target node
            original_target = node_group.original_incoming_targets.get(conn_id)
            if original_target is None:
                continue

            # Create proxy parameter name to find it in the index
            sanitized_node_name = original_target.name.replace(" ", "_")
            proxy_param_name = f"{sanitized_node_name}__{conn.target_parameter.name}"

            # Remove proxy from incoming index (using proxy parameter name)
            if (
                proxy_node.name in connections.incoming_index
                and proxy_param_name in connections.incoming_index[proxy_node.name]
            ):
                connections.incoming_index[proxy_node.name][proxy_param_name].remove(conn_id)

            # Restore connection to original target node
            conn.target_node = original_target

            # Add back to original target node's incoming index (using original parameter name)
            connections.incoming_index.setdefault(conn.target_node.name, {}).setdefault(
                conn.target_parameter.name, []
            ).append(conn_id)

        # Restore external outgoing connections (original source node -> proxy)
        for conn in node_group.external_outgoing_connections:
            conn_id = id(conn)

            # Get original source node
            original_source = node_group.original_outgoing_sources.get(conn_id)
            if original_source is None:
                continue

            # Create proxy parameter name to find it in the index
            sanitized_node_name = original_source.name.replace(" ", "_")
            proxy_param_name = f"{sanitized_node_name}__{conn.source_parameter.name}"

            # Remove proxy from outgoing index (using proxy parameter name)
            if (
                proxy_node.name in connections.outgoing_index
                and proxy_param_name in connections.outgoing_index[proxy_node.name]
            ):
                connections.outgoing_index[proxy_node.name][proxy_param_name].remove(conn_id)

            # Restore connection to original source node
            conn.source_node = original_source

            # Add back to original source node's outgoing index (using original parameter name)
            connections.outgoing_index.setdefault(conn.source_node.name, {}).setdefault(
                conn.source_parameter.name, []
            ).append(conn_id)

        # Deregister proxy node from ObjectManager
        obj_manager = GriptapeNodes.ObjectManager()
        if obj_manager.has_object_with_name(proxy_node.name):
            del obj_manager._name_to_objects[proxy_node.name]

        logger.debug(
            "Cleaned up proxy node '%s' for group '%s' - restored %d connections",
            proxy_node.name,
            node_group.group_id,
            len(node_group.external_incoming_connections) + len(node_group.external_outgoing_connections),
        )

    @staticmethod
    def get_next_control_output_for_non_local_execution(node: BaseNode) -> Parameter | None:
        for param_name, value in node.parameter_output_values.items():
            parameter = node.get_parameter_by_name(param_name)
            if (
                parameter is not None
                and parameter.type == ParameterTypeBuiltin.CONTROL_TYPE.value
                and value == CONTROL_INPUT_PARAMETER
            ):
                # This is the parameter
                logger.debug(
                    "Parallel Resolution: Found control output parameter '%s' for non-local execution", param_name
                )
                return parameter
        return None

    @staticmethod
    def get_next_control_graph(context: ParallelResolutionContext, node: BaseNode, network_name: str) -> None:
        """Get next control flow nodes and add them to the DAG graph."""
        flow_manager = GriptapeNodes.FlowManager()

        # Early returns for various conditions
        if ExecuteDagState._should_skip_control_flow(context, node, network_name, flow_manager):
            return
        if node.get_parameter_value(node.execution_environment.name) != LOCAL_EXECUTION:
            next_output = ExecuteDagState.get_next_control_output_for_non_local_execution(node)
        else:
            next_output = node.get_next_control_output()
        if node.get_parameter_value(node.execution_environment.name) != LOCAL_EXECUTION:
            next_output = ExecuteDagState.get_next_control_output_for_non_local_execution(node)
        else:
            next_output = node.get_next_control_output()
        if next_output is not None:
            ExecuteDagState._process_next_control_node(context, node, next_output, network_name, flow_manager)

    @staticmethod
    def _should_skip_control_flow(
        context: ParallelResolutionContext, node: BaseNode, network_name: str, flow_manager: FlowManager
    ) -> bool:
        """Check if control flow processing should be skipped."""
        # Get network once to avoid duplicate lookups
        if context.dag_builder is None:
            msg = "DAG builder is not initialized"
            raise ValueError(msg)
        network = context.dag_builder.graphs.get(network_name, None)
        if network is None:
            msg = f"Network {network_name} not found in DAG builder"
            raise ValueError(msg)
        if flow_manager.global_single_node_resolution:
            # Clean up nodes from emptied graphs in single node resolution mode
            if len(network) == 0 and context.dag_builder is not None:
                context.dag_builder.cleanup_empty_graph_nodes(network_name)
                ExecuteDagState._emit_involved_nodes_update(context)
            return True

        return bool(len(network) > 0 or node.stop_flow)

    @staticmethod
    def _process_next_control_node(
        context: ParallelResolutionContext,
        node: BaseNode,
        next_output: Parameter,
        network_name: str,
        flow_manager: FlowManager,
    ) -> None:
        """Process the next control node in the flow."""
        node_connection = flow_manager.get_connections().get_connected_node(node, next_output)
        if node_connection is not None:
            next_node, next_parameter = node_connection
            # Set entry control parameter
            logger.debug(
                "Parallel Resolution: Setting entry control parameter for node '%s' to '%s'",
                next_node.name,
                next_parameter.name if next_parameter else None,
            )
            next_node.set_entry_control_parameter(next_parameter)
            next_node, next_parameter = node_connection
            # Set entry control parameter
            logger.debug(
                "Parallel Resolution: Setting entry control parameter for node '%s' to '%s'",
                next_node.name,
                next_parameter.name if next_parameter else None,
            )
            next_node.set_entry_control_parameter(next_parameter)
            # Prepare next node for execution
            if not next_node.lock:
                next_node.make_node_unresolved(
                    current_states_to_trigger_change_event=set(
                        {
                            NodeResolutionState.UNRESOLVED,
                            NodeResolutionState.RESOLVED,
                            NodeResolutionState.RESOLVING,
                        }
                    )
                )
                GriptapeNodes.EventManager().put_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(payload=CurrentControlNodeEvent(node_name=next_node.name))
                    )
                )
            ExecuteDagState._add_and_queue_nodes(context, next_node, network_name)

    @staticmethod
    def _emit_involved_nodes_update(context: ParallelResolutionContext) -> None:
        """Emit update of involved nodes based on current DAG state."""
        if context.dag_builder is not None:
            involved_nodes = list(context.node_to_reference.keys())
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=InvolvedNodesEvent(involved_nodes=involved_nodes))
                )
            )

    @staticmethod
    def _add_and_queue_nodes(context: ParallelResolutionContext, next_node: BaseNode, network_name: str) -> None:
        """Add nodes to DAG and queue them if ready."""
        if context.dag_builder is not None:
            added_nodes = context.dag_builder.add_node_with_dependencies(next_node, network_name)
            if next_node not in added_nodes:
                added_nodes.append(next_node)

            # Queue nodes that are ready for execution
            if added_nodes:
                for added_node in added_nodes:
                    ExecuteDagState._try_queue_waiting_node(context, added_node.name)

    @staticmethod
    def _try_queue_waiting_node(context: ParallelResolutionContext, node_name: str) -> None:
        """Try to queue a specific waiting node if it can now be queued."""
        if context.dag_builder is None:
            logger.warning("DAG builder is None - cannot check queueing for node '%s'", node_name)
            return

        if node_name not in context.node_to_reference:
            logger.warning("Node '%s' not found in node_to_reference - cannot check queueing", node_name)
            return

        dag_node = context.node_to_reference[node_name]

        # Only check nodes that are currently waiting
        if dag_node.node_state == NodeState.WAITING:
            can_queue = context.dag_builder.can_queue_control_node(dag_node)
            if can_queue:
                dag_node.node_state = NodeState.QUEUED

    @staticmethod
    async def collect_values_from_upstream_nodes(node_reference: DagNode) -> None:
        """Collect output values from resolved upstream nodes and pass them to the current node.

        This method iterates through all input parameters of the current node, finds their
        connected upstream nodes, and if those nodes are resolved, retrieves their output
        values and passes them through using SetParameterValueRequest.

        Args:
            node_reference (DagOrchestrator.DagNode): The node to collect values for.
        """
        current_node = node_reference.node_reference
        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            # Get the connected upstream node for this parameter
            upstream_connection = connections.get_connected_node(current_node, parameter, direction=Direction.UPSTREAM)
            upstream_connection = connections.get_connected_node(current_node, parameter, direction=Direction.UPSTREAM)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # If the upstream node is resolved, collect its output value
                if upstream_parameter.name in upstream_node.parameter_output_values:
                    output_value = upstream_node.parameter_output_values[upstream_parameter.name]
                else:
                    output_value = upstream_node.get_parameter_value(upstream_parameter.name)

                # Pass the value through using the same mechanism as normal resolution
                result = await GriptapeNodes.get_instance().ahandle_request(
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
                    msg = f"Failed to set value for parameter '{parameter.name}' on node '{current_node.name}': {result.result_details}"
                    logger.error(msg)
                    raise RuntimeError(msg)
                result = await GriptapeNodes.get_instance().ahandle_request(
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
                    msg = f"Failed to set value for parameter '{parameter.name}' on node '{current_node.name}': {result.result_details}"
                    logger.error(msg)
                    raise RuntimeError(msg)

    @staticmethod
    def build_node_states(context: ParallelResolutionContext) -> tuple[set[str], set[str], set[str]]:
        networks = context.networks
        leaf_nodes = set()
        for network in networks.values():
            # Check and see if there are leaf nodes that are cancelled.
            # Reinitialize leaf nodes since maybe we changed things up.
            # We removed nodes from the network. There may be new leaf nodes.
            # Add all leaf nodes from all networks (using set union to avoid duplicates)
            leaf_nodes.update([n for n in network.nodes() if network.in_degree(n) == 0])
        canceled_nodes = set()
        queued_nodes = set()
        for node in leaf_nodes:
            node_reference = context.node_to_reference[node]
            # If the node is locked, mark it as done so it skips execution
            if node_reference.node_reference.lock:
                node_reference.node_state = NodeState.DONE
                continue
            node_state = node_reference.node_state
            if node_state == NodeState.CANCELED:
                canceled_nodes.add(node)
            elif node_state == NodeState.QUEUED:
                queued_nodes.add(node)
        return canceled_nodes, queued_nodes, leaf_nodes

    @staticmethod
    async def pop_done_states(context: ParallelResolutionContext) -> None:
        networks = context.networks
        handled_nodes = set()  # Track nodes we've already processed to avoid duplicates

        for network_name, network in networks.items():
            # Check and see if there are leaf nodes that are cancelled.
            # Reinitialize leaf nodes since maybe we changed things up.
            # We removed nodes from the network. There may be new leaf nodes.
            leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]
            for node in leaf_nodes:
                node_reference = context.node_to_reference[node]
                node_state = node_reference.node_state
                # If the node is locked, mark it as done so it skips execution
                if node_reference.node_reference.lock or node_state == NodeState.DONE:
                    node_reference.node_state = NodeState.DONE
                    network.remove_node(node)

                    # Only call handle_done_nodes once per node (first network that processes it)
                    if node not in handled_nodes:
                        handled_nodes.add(node)
                        await ExecuteDagState.handle_done_nodes(context, context.node_to_reference[node], network_name)

            # After processing completions in this network, check if any remaining leaf nodes can now be queued
            remaining_leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]

            for leaf_node in remaining_leaf_nodes:
                if leaf_node in context.node_to_reference:
                    node_state = context.node_to_reference[leaf_node].node_state
                ExecuteDagState._try_queue_waiting_node(context, leaf_node)

    @staticmethod
    async def execute_node(current_node: DagNode, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            executor = GriptapeNodes.FlowManager().node_executor
            await executor.execute(current_node.node_reference)

    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        # Start DAG execution after resolution is complete
        for node in context.node_to_reference.values():
            # Only queue nodes that are waiting - preserve state of already processed nodes.
            if node.node_state == NodeState.WAITING:
                node.node_state = NodeState.QUEUED

        context.workflow_state = WorkflowState.NO_ERROR

        if not context.paused:
            return ExecuteDagState
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: C901, PLR0911, PLR0915
        # Check if execution is paused
        if context.paused:
            return None

        # Check if DAG execution is complete
        # Check and see if there are leaf nodes that are cancelled.
        # Reinitialize leaf nodes since maybe we changed things up.
        # We removed nodes from the network. There may be new leaf nodes.
        canceled_nodes, queued_nodes, leaf_nodes = ExecuteDagState.build_node_states(context)
        # We have no more leaf nodes. Quit early.
        if not leaf_nodes:
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return DagCompleteState
        if len(canceled_nodes) == len(leaf_nodes):
            # All leaf nodes are cancelled.
            # Set state to workflow complete.
            context.workflow_state = WorkflowState.CANCELED
            return DagCompleteState
        # Are there any in the queued state?
        for node in queued_nodes:
            # Process all queued nodes - the async semaphore will handle concurrency limits
            node_reference = context.node_to_reference[node]

            # Collect parameter values from upstream nodes before executing
            try:
                await ExecuteDagState.collect_values_from_upstream_nodes(node_reference)
            except Exception as e:
                logger.exception("Error collecting parameter values for node '%s'", node_reference.node_reference.name)
                context.error_message = (
                    f"Parameter passthrough failed for node '{node_reference.node_reference.name}': {e}"
                )
                context.workflow_state = WorkflowState.ERRORED
                return ErrorState

            # Clear all of the current output values but don't broadcast the clearing.
            # to avoid any flickering in subscribers (UI).
            node_reference.node_reference.parameter_output_values.silent_clear()
            exceptions = node_reference.node_reference.validate_before_node_run()
            if exceptions:
                msg = f"Canceling flow run. Node '{node_reference.node_reference.name}' encountered problems: {exceptions}"
                logger.error(msg)
                return ErrorState

            def on_task_done(task: asyncio.Task) -> None:
                if task in context.task_to_node:
                    node = context.task_to_node[task]
                    node.node_state = NodeState.DONE

            # Execute the node asynchronously
            logger.debug(
                "CREATING EXECUTION TASK for node '%s' - this should only happen once per node!",
                node_reference.node_reference.name,
            )
            node_task = asyncio.create_task(ExecuteDagState.execute_node(node_reference, context.async_semaphore))
            # Add a callback to set node to done when task has finished.
            context.task_to_node[node_task] = node_reference
            node_reference.task_reference = node_task
            node_task.add_done_callback(lambda t: on_task_done(t))
            node_reference.node_state = NodeState.PROCESSING
            node_reference.node_reference.state = NodeResolutionState.RESOLVING

            # Send an event that this is a current data node:

            await GriptapeNodes.EventManager().aput_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=node)))
            )

        # Wait for a task to finish - only if there are tasks running
        if context.task_to_node:
            done, _ = await asyncio.wait(context.task_to_node.keys(), return_when=asyncio.FIRST_COMPLETED)
            # Check for task exceptions and handle them properly
            for task in done:
                if task.cancelled():
                    # Task was cancelled - this is expected during flow cancellation
                    context.task_to_node.pop(task)
                    logger.info("Task execution was cancelled.")
                    return ErrorState
                if task.exception():
                    exc = task.exception()
                    dag_node = context.task_to_node.get(task)
                    node_name = dag_node.node_reference.name if dag_node else "Unknown"
                    node_type = dag_node.node_reference.__class__.__name__ if dag_node else "Unknown"

                    logger.exception(
                        "Task execution failed for node '%s' (type: %s) in flow '%s'. Exception: %s",
                        node_name,
                        node_type,
                        context.flow_name,
                        exc,
                    )

                    dag_node = context.task_to_node.get(task)
                    node_name = dag_node.node_reference.name if dag_node else "Unknown"
                    node_type = dag_node.node_reference.__class__.__name__ if dag_node else "Unknown"

                    logger.exception(
                        "Task execution failed for node '%s' (type: %s) in flow '%s'. Exception: %s",
                        node_name,
                        node_type,
                        context.flow_name,
                        exc,
                    )

                    context.task_to_node.pop(task)
                    context.error_message = f"Task execution failed for node '{node_name}': {exc}"
                    context.workflow_state = WorkflowState.ERRORED
                    return ErrorState
                    context.error_message = f"Task execution failed for node '{node_name}': {exc}"
                    context.workflow_state = WorkflowState.ERRORED
                    return ErrorState
                context.task_to_node.pop(task)
        # Once a task has finished, loop back to the top.
        await ExecuteDagState.pop_done_states(context)
        # Remove all nodes that are done
        if context.paused:
            return None
        return ExecuteDagState


class ErrorState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)

        # Clean up any proxy nodes that failed before completion
        from griptape_nodes.exe_types.node_types import NodeGroupProxyNode

        for node in context.node_to_reference.values():
            # Clean up proxy nodes that were processing or queued
            if isinstance(node.node_reference, NodeGroupProxyNode) and node.node_state in (
                NodeState.PROCESSING,
                NodeState.QUEUED,
            ):
                logger.info("Cleaning up proxy node '%s' that failed during execution", node.node_reference.name)
                ExecuteDagState._cleanup_proxy_node(node.node_reference)

            # Cancel all nodes that haven't yet begun processing.
            if node.node_state == NodeState.QUEUED:
                node.node_state = NodeState.CANCELED

        # Shut down and cancel all threads/tasks that haven't yet ran. Currently running ones will not be affected.
        # Cancel async tasks
        for task in list(context.task_to_node.keys()):
            if not task.done():
                task.cancel()
        return ErrorState

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
        # Don't modify lists while iterating through them.
        task_to_node = context.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        # Handle async tasks
        task_to_node = context.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        if len(task_to_node) == 0:
            # Finish up. We failed.
            context.workflow_state = WorkflowState.ERRORED
            context.networks.clear()
            context.node_to_reference.clear()
            context.task_to_node.clear()
            return DagCompleteState
        # Let's continue going through until everything is cancelled.
        return ErrorState


class DagCompleteState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        # Clear the DAG builder so we don't have any leftover nodes in node_to_reference.
        if context.dag_builder is not None:
            context.dag_builder.clear()
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class ParallelResolutionMachine(FSM[ParallelResolutionContext]):
    """State machine for building DAG structure without execution."""

    def __init__(
        self, flow_name: str, max_nodes_in_parallel: int | None = None, dag_builder: DagBuilder | None = None
    ) -> None:
        resolution_context = ParallelResolutionContext(
            flow_name, max_nodes_in_parallel=max_nodes_in_parallel, dag_builder=dag_builder
        )
        super().__init__(resolution_context)

    async def resolve_node(self, node: BaseNode | None = None) -> None:  # noqa: ARG002
        """Execute the DAG structure using the existing DagBuilder."""
        if self.context.dag_builder is None:
            self.context.dag_builder = GriptapeNodes.FlowManager().global_dag_builder
        await self.start(ExecuteDagState)

    async def cancel_all_nodes(self) -> None:
        """Cancel all executing tasks and set cancellation flags on all nodes."""
        # Set cancellation flag on all nodes being tracked
        for dag_node in self.context.node_to_reference.values():
            dag_node.node_reference.request_cancellation()

        # Cancel all running tasks
        tasks = list(self.context.task_to_node.keys())
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

    def change_debug_mode(self, *, debug_mode: bool) -> None:
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is DagCompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None

    def get_last_resolved_node(self) -> BaseNode | None:
        """Get the last node that was resolved in the DAG execution."""
        return self._context.last_resolved_node
