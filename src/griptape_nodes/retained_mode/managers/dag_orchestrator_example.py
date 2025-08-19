from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

import networkx as nx
from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from concurrent.futures import Future

    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class WorkflowState(Enum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"


class NodeState(Enum):
    """Individual node execution states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    ERRORED = "errored"
    WAITING = "waiting"


class ExecutionResult(Enum):
    """Final execution results."""

    COMPLETED_SUCCESSFULLY = "completed_successfully"
    ERRORED = "errored"

# orchestrator attached to each flow, owned by griptape nodes
class DagOrchestrator:
    """Main DAG structure containing nodes and edges."""

    # The generated network of nodes
    network: nx.DiGraph
    # The node to reference mapping. Includes node and thread references.
    node_to_reference: dict[str, DagOrchestrator.DagNode]
    # The queued, running, and completed nodes.
    # TODO: These will disappear.
    queued_nodes: ClassVar[list[str]] = []
    running_nodes: ClassVar[list[str]] = []
    cancelled_nodes: ClassVar[list[str]] = []
    # NOTE: Threading will be implemented later

    def __init__(self) -> None:
        """Initialize the DagOrchestrator singleton with initialization guard."""
        # Initialize only if our network hasn't been created yet (like GriptapeNodes pattern)
        self.network = nx.DiGraph()
        # Node to reference will also contain node state.
        self.node_to_reference = {}

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        node_reference: BaseNode
        thread_reference: Future | None = field(default=None)
        node_state: NodeState = field(default=NodeState.WAITING)

    @classmethod
    def execute_dag_workflow(cls) -> tuple[ExecutionResult, list[str]]:
        """Execute the DAG workflow using topological sorting approach.

        Based on the provided pseudocode but without threading implementation yet.

        Returns:
            Tuple of (ExecutionResult, error_list)
        """
        # Validate DAG state before execution
        dag_instance = cls.get_instance()
        logger.info("EXECUTE_DAG: Starting workflow execution. Instance ID: %s", id(dag_instance))
        logger.info("EXECUTE_DAG: Pre-execution state check...")
        cls.debug_dag_state()

        if not cls.network.nodes():
            error_msg = "DAG network is empty - no nodes to execute. DAG must be built before execution."
            logger.error("EXECUTE_DAG: %s", error_msg)
            return ExecutionResult.ERRORED, [error_msg]

        if not cls.node_to_reference:
            error_msg = "node_to_reference is empty - DAG references missing. DAG must be built before execution."
            logger.error("EXECUTE_DAG: %s", error_msg)
            return ExecutionResult.ERRORED, [error_msg]

        # Initialize workflow state
        workflow_state = WorkflowState.NO_ERROR
        thread_pool = ThreadPoolExecutor(max_workers=3)
        error_list: list[str] = []
        while workflow_state == WorkflowState.NO_ERROR and workflow_state != WorkflowState.WORKFLOW_COMPLETE:
            # Find leaf nodes not in canceled state using topological approach
            # Don't modify list while iterating
            # state of node maintained as a variable in the loop
            running_nodes = cls.running_nodes.copy()
            for node in running_nodes:
                # Check the future and see if it's completed.
                thread_reference = cls.node_to_reference[node].thread_reference
                # The thread has finished running now.
                # TODO: UPDATE TO USE AS_COMPLETED
                if thread_reference is not None and thread_reference.done():
                    # Remove from running nodes
                    cls.running_nodes.remove(node)
                    # Remove the node from the network
                    cls.network.remove_node(node)
                    # return to thread refernces 
                    if thread_reference.exception() is not None:
                        error_list.append(str(thread_reference.exception()))
                        # Add to cancelled nodes
                        cls.cancelled_nodes.append(node)
                        workflow_state = WorkflowState.ERRORED
                        break
            # Mark nodes that are leaf nodes and ready to go as queued.
            for node in cls.network.nodes():
                if cls.network.in_degree(node) == 0:
                    cls.queued_nodes.append(node)

            # No more nodes left in the queue.
            if len(cls.queued_nodes) == 0:
                workflow_state = WorkflowState.WORKFLOW_COMPLETE
                break

            # Threading implementation will go here:
            while len(cls.queued_nodes) > 0 and thread_pool._work_queue.__sizeof__() < thread_pool._max_workers:
                node = cls.queued_nodes.pop(0)
                node_reference = cls.node_to_reference[node].node_reference
                # Add to running nodes
                future = thread_pool.submit(cls.execute_node, node_reference)
                # Set future on node reference
                cls.node_to_reference[node].thread_reference = future
                cls.running_nodes.append(node)
            # Is there a thread available? If so, assign it to the next node until no more threads are available.

        # Handle errored workflow state
        if workflow_state == WorkflowState.ERRORED:
            # Cancel and shut down everyrhing
            thread_pool.shutdown(wait=True, cancel_futures=True)
            running_nodes = cls.running_nodes.copy()
            # Wait for all of the threads to cancel/shut down.
            # add nodes to cancelled state
            while len(running_nodes) > 0:
                for node in cls.running_nodes:
                    thread_reference = cls.node_to_reference[node].thread_reference
                    if thread_reference is not None and (thread_reference.cancelled() or thread_reference.done()):
                        running_nodes.remove(node)
                        cls.cancelled_nodes.append(node)
                cls.running_nodes = running_nodes
            return ExecutionResult.ERRORED, error_list

        # Handle final workflow state
        if workflow_state == WorkflowState.WORKFLOW_COMPLETE:
            return ExecutionResult.COMPLETED_SUCCESSFULLY, []
        return ExecutionResult.ERRORED, error_list


    @classmethod
    def execute_node(cls, current_node: BaseNode) -> None:
        """Execute a single node by collecting upstream values and running the node.

        This method replicates the ExecuteNodeState logic for node execution.
        It's designed to be called from worker threads during DAG execution.

        Args:
            current_node: The node to execute

        Raises:
            RuntimeError: If node execution fails
        """
        try:
            # Skip execution if node is locked
            if current_node.lock:
                logger.info("Node '%s' is locked, skipping execution.", current_node.name)
                return

            # Collect values from upstream nodes
            cls._collect_values_from_upstream_nodes(current_node)

            # Clear existing output values
            cls._clear_parameter_output_values(current_node)

            # Set parameter values from defaults if not already set
            for parameter in current_node.parameters:
                if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                    continue
                if parameter.name not in current_node.parameter_values:
                    value = current_node.get_parameter_value(parameter.name)
                    if value is not None:
                        current_node.set_parameter_value(parameter.name, value)

                # Publish parameter value events
                if parameter.name in current_node.parameter_values:
                    parameter_value = current_node.get_parameter_value(parameter.name)
                    data_type = parameter.type
                    if data_type is None:
                        data_type = ParameterTypeBuiltin.NONE.value
                    EventBus.publish_event(
                        ExecutionGriptapeNodeEvent(
                            wrapped_event=ExecutionEvent(
                                payload=ParameterValueUpdateEvent(
                                    node_name=current_node.name,
                                    parameter_name=parameter.name,
                                    data_type=data_type,
                                    value=TypeValidator.safe_serialize(parameter_value),
                                )
                            )
                        )
                    )

            # Validate node before execution
            exceptions = current_node.validate_before_node_run()
            if exceptions:
                msg = f"Node '{current_node.name}' validation failed: {exceptions}"
                raise RuntimeError(msg)

            # Publish node start event
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
                )
            )
            logger.info("Node '%s' is processing.", current_node.name)

            # Execute the node - NOTE: This is synchronous, no generator handling yet
            current_node.process()

            # Mark node as resolved
            current_node.state = NodeResolutionState.RESOLVED
            logger.info("Node '%s' finished processing.", current_node.name)

            # Publish output values
            for parameter_name, value in current_node.parameter_output_values.items():
                parameter = current_node.get_parameter_by_name(parameter_name)
                if parameter is None:
                    err = f"Node '{current_node.name}' specified Parameter '{parameter_name}', but no such Parameter found."
                    raise KeyError(err)
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                EventBus.publish_event(
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

            # Publish node resolved event
            library = LibraryRegistry.get_libraries_with_node_type(current_node.__class__.__name__)
            library_name = library[0] if len(library) == 1 else None
            EventBus.publish_event(
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

            # Publish node finish event
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                )
            )

        except Exception as e:
            # Mark node as unresolved on error
            current_node.make_node_unresolved(
                current_states_to_trigger_change_event={
                    NodeResolutionState.UNRESOLVED,
                    NodeResolutionState.RESOLVED,
                    NodeResolutionState.RESOLVING,
                }
            )

            # Publish node finish event even on error
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                )
            )

            logger.exception("Error processing node '%s'", current_node.name)
            msg = f"Node '{current_node.name}' encountered a problem: {e}"
            raise RuntimeError(msg) from e

    @classmethod
    def _collect_values_from_upstream_nodes(cls, current_node: BaseNode) -> None:
        """Collect output values from resolved upstream nodes and pass them to the current node."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            # Skip control type parameters
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue

            # Get the connected upstream node for this parameter
            upstream_connection = connections.get_connected_node(current_node, parameter)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # Get output value from upstream node
                if upstream_parameter.name in upstream_node.parameter_output_values:
                    output_value = upstream_node.parameter_output_values[upstream_parameter.name]
                else:
                    output_value = upstream_node.get_parameter_value(upstream_parameter.name)

                # Pass the value through using SetParameterValueRequest
                GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=parameter.name,
                        node_name=current_node.name,
                        value=output_value,
                        data_type=upstream_parameter.output_type,
                    )
                )

    @classmethod
    def _clear_parameter_output_values(cls, current_node: BaseNode) -> None:
        """Clear all parameter output values for the current node."""
        for parameter_name in current_node.parameter_output_values.copy():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Node '{current_node.name}' has output value for unknown parameter '{parameter_name}'."
                raise ValueError(err)
            parameter_type = parameter.type
            if parameter_type is None:
                parameter_type = ParameterTypeBuiltin.NONE.value
            payload = ParameterValueUpdateEvent(
                node_name=current_node.name,
                parameter_name=parameter_name,
                data_type=parameter_type,
                value=None,
            )
            EventBus.publish_event(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
        current_node.parameter_output_values.clear()

    @classmethod
    def debug_dag_state(cls) -> None:
        """Debug method to inspect current DAG state and log details."""
        logger.info("=== DAG ORCHESTRATOR DEBUG STATE ===")
        logger.info("Singleton Instance ID: %s", id(cls))
        logger.info("Network nodes count: %d", len(cls.network.nodes()))
        logger.info("Network edges count: %d", len(cls.network.edges()))
        logger.info("node_to_reference count: %d", len(cls.node_to_reference))
        logger.info("queued_nodes count: %d", len(cls.queued_nodes))
        logger.info("running_nodes count: %d", len(cls.running_nodes))
        logger.info("cancelled_nodes count: %d", len(cls.cancelled_nodes))

        if cls.network.nodes():
            logger.info("Network nodes: %s", list(cls.network.nodes()))
        if cls.network.edges():
            logger.info("Network edges: %s", list(cls.network.edges()))
        if cls.node_to_reference:
            logger.info("node_to_reference keys: %s", list(cls.node_to_reference.keys()))

        logger.info("=== END DAG ORCHESTRATOR DEBUG STATE ===")
