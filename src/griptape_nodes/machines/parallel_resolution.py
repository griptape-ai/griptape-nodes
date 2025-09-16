from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import Parameter, ParameterType, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.dag_builder import NodeState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeResolvedEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

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

    def __init__(
        self, flow_name: str, max_nodes_in_parallel: int | None = None, dag_builder: DagBuilder | None = None
    ) -> None:
        self.flow_name = flow_name
        self.paused = False
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR
        self.dag_builder = dag_builder

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

        # Clear DAG builder state to allow re-adding nodes on subsequent runs
        if self.dag_builder:
            self.dag_builder.clear()


class ExecuteDagState(State):
    @staticmethod
    async def handle_done_nodes(context: ParallelResolutionContext, done_node: DagNode, network_name: str) -> None:
        current_node = done_node.node_reference
        logger.info("HANDLING COMPLETION of node '%s' from network '%s'", current_node.name, network_name)

        # Check if node was already resolved (shouldn't happen)
        if current_node.state == NodeResolutionState.RESOLVED:
            logger.error(
                "DUPLICATE COMPLETION DETECTED: Node '%s' was already RESOLVED but handle_done_nodes was called again from network '%s'. This should not happen!",
                current_node.name,
                network_name,
            )
            return

        # Publish all parameter updates.
        current_node.state = NodeResolutionState.RESOLVED
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
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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

    @staticmethod
    def get_next_control_graph(context: ParallelResolutionContext, node: BaseNode, network_name: str) -> None:
        """Get next control flow nodes and add them to the DAG graph."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        flow_manager = GriptapeNodes.FlowManager()

        # Early returns for various conditions
        if ExecuteDagState._should_skip_control_flow(context, node, network_name, flow_manager):
            return

        next_output = node.get_next_control_output()
        if next_output is not None:
            ExecuteDagState._process_next_control_node(context, node, next_output, network_name, flow_manager)

    @staticmethod
    def _should_skip_control_flow(
        context: ParallelResolutionContext, node: BaseNode, network_name: str, flow_manager: FlowManager
    ) -> bool:
        """Check if control flow processing should be skipped."""
        if flow_manager.global_single_node_resolution:
            return True

        if context.dag_builder is not None:
            network = context.dag_builder.graphs.get(network_name, None)
            if network is not None and len(network) > 0:
                return True

        if node.stop_flow:
            node.stop_flow = False
            return True

        return False

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
            next_node, _ = node_connection

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

            ExecuteDagState._add_and_queue_nodes(context, next_node, network_name)

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
                    ExecuteDagState._try_queue_waiting_node(context, added_node.name, network_name)

    @staticmethod
    def _try_queue_waiting_node(context: ParallelResolutionContext, node_name: str, network_name: str) -> None:
        """Try to queue a specific waiting node if it can now be queued."""
        if context.dag_builder is None:
            logger.warning("DAG builder is None - cannot check queueing for node '%s'", node_name)
            return

        if node_name not in context.node_to_reference:
            logger.warning("Node '%s' not found in node_to_reference - cannot check queueing", node_name)
            return

        dag_node = context.node_to_reference[node_name]
        node_resolution_state = dag_node.node_reference.state

        logger.info(
            "Checking node '%s' for queueing - current state: %s, resolution state: %s",
            node_name,
            dag_node.node_state,
            node_resolution_state,
        )

        # Only check nodes that are currently waiting
        if dag_node.node_state == NodeState.WAITING:
            logger.info(
                "Node '%s' is WAITING - checking if it can be queued from network '%s'", node_name, network_name
            )

            can_queue = context.dag_builder.can_queue_control_node(dag_node, network_name)
            if can_queue:
                logger.info("SUCCESS: Queueing node '%s' for execution from network '%s'", node_name, network_name)
                dag_node.node_state = NodeState.QUEUED
            else:
                logger.info(
                    "BLOCKED: Node '%s' cannot be queued yet from network '%s' - waiting for control flow dependencies",
                    node_name,
                    network_name,
                )
        else:
            logger.info("Node '%s' has state %s - not eligible for queueing", node_name, dag_node.node_state)

    @staticmethod
    async def collect_values_from_upstream_nodes(node_reference: DagNode) -> None:
        """Collect output values from resolved upstream nodes and pass them to the current node.

        This method iterates through all input parameters of the current node, finds their
        connected upstream nodes, and if those nodes are resolved, retrieves their output
        values and passes them through using SetParameterValueRequest.

        Args:
            node_reference (DagOrchestrator.DagNode): The node to collect values for.
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        current_node = node_reference.node_reference
        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            # Skip control type parameters
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue

            # Get the connected upstream node for this parameter
            upstream_connection = connections.get_connected_node(current_node, parameter)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # If the upstream node is resolved, collect its output value
                if upstream_parameter.name in upstream_node.parameter_output_values:
                    output_value = upstream_node.parameter_output_values[upstream_parameter.name]
                else:
                    output_value = upstream_node.get_parameter_value(upstream_parameter.name)

                # Pass the value through using the same mechanism as normal resolution
                # Skip propagation for Control Parameters as they should not receive values
                if (
                    ParameterType.attempt_get_builtin(upstream_parameter.output_type)
                    != ParameterTypeBuiltin.CONTROL_TYPE
                ):
                    await GriptapeNodes.get_instance().ahandle_request(
                        SetParameterValueRequest(
                            parameter_name=parameter.name,
                            node_name=current_node.name,
                            value=output_value,
                            data_type=upstream_parameter.output_type,
                            incoming_connection_source_node_name=upstream_node.name,
                            incoming_connection_source_parameter_name=upstream_parameter.name,
                        )
                    )

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
                        logger.info(
                            "Node '%s' completed - calling handle_done_nodes from network '%s' (first time)",
                            node,
                            network_name,
                        )
                        handled_nodes.add(node)
                        await ExecuteDagState.handle_done_nodes(context, context.node_to_reference[node], network_name)
                    else:
                        logger.info(
                            "Node '%s' completed - already handled, skipping handle_done_nodes for network '%s'",
                            node,
                            network_name,
                        )

            # After processing completions in this network, check if any remaining leaf nodes can now be queued
            remaining_leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]
            logger.info(
                "Network '%s' has %d remaining leaf nodes after cleanup: %s",
                network_name,
                len(remaining_leaf_nodes),
                remaining_leaf_nodes,
            )

            for leaf_node in remaining_leaf_nodes:
                if leaf_node in context.node_to_reference:
                    node_state = context.node_to_reference[leaf_node].node_state
                    logger.info("Leaf node '%s' in network '%s' has state: %s", leaf_node, network_name, node_state)
                ExecuteDagState._try_queue_waiting_node(context, leaf_node, network_name)

    @staticmethod
    async def execute_node(current_node: DagNode, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            await current_node.node_reference.aprocess()

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
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: C901, PLR0911
        # Check if execution is paused
        if context.paused:
            return None

        # Check if DAG execution is complete
        # Check and see if there are leaf nodes that are cancelled.
        # Reinitialize leaf nodes since maybe we changed things up.
        # We removed nodes from the network. There may be new leaf nodes.
        canceled_nodes, queued_nodes, leaf_nodes = ExecuteDagState.build_node_states(context)
        logger.info(
            "Node states - Leaf nodes: %d, Queued: %d, Canceled: %d",
            len(leaf_nodes),
            len(queued_nodes),
            len(canceled_nodes),
        )
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
            logger.info(
                "Processing queued node '%s' - current resolution state: %s", node, node_reference.node_reference.state
            )

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

            # Check if node is already being processed (shouldn't happen)
            if node_reference.node_reference.state == NodeResolutionState.RESOLVING:
                logger.error(
                    "DUPLICATE EXECUTION DETECTED: Node '%s' is already RESOLVING but was queued for execution again. This should not happen!",
                    node_reference.node_reference.name,
                )
                continue

            # Check if node is already resolved (also shouldn't happen for queued nodes)
            if node_reference.node_reference.state == NodeResolutionState.RESOLVED:
                logger.error(
                    "DUPLICATE EXECUTION DETECTED: Node '%s' is already RESOLVED but was queued for execution again. This should not happen!",
                    node_reference.node_reference.name,
                )
                continue

            # Execute the node asynchronously
            logger.info(
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
            logger.info("Node '%s' state changed to PROCESSING and RESOLVING", node_reference.node_reference.name)

            # Send an event that this is a current data node:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            await GriptapeNodes.EventManager().aput_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=node)))
            )
            # Wait for a task to finish
        done, _ = await asyncio.wait(context.task_to_node.keys(), return_when=asyncio.FIRST_COMPLETED)
        # Prevent task being removed before return
        for task in done:
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
        for node in context.node_to_reference.values():
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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        if self.context.dag_builder is None:
            self.context.dag_builder = GriptapeNodes.FlowManager().global_dag_builder
        await self.start(ExecuteDagState)

    def change_debug_mode(self, *, debug_mode: bool) -> None:
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is DagCompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None
