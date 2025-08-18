from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
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


class ExecutionResult(Enum):
    """Final execution results."""

    COMPLETED_SUCCESSFULLY = "completed_successfully"
    ERRORED = "errored"


class DagOrchestrator(metaclass=SingletonMeta):
    """Main DAG structure containing nodes and edges."""

    # The generated network of nodes
    network: ClassVar[nx.DiGraph] = nx.DiGraph()
    # The node to reference mapping. Includes node and thread references.
    node_to_reference: ClassVar[dict[str, DagOrchestrator.DagNode]] = {}
    # The queued, running, and completed nodes.
    queued_nodes: ClassVar[list[str]] = []
    running_nodes: ClassVar[list[str]] = []
    cancelled_nodes: ClassVar[list[str]] = []
    # NOTE: Threading will be implemented later

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        node_reference: BaseNode
        thread_reference: Future | None = field(default=None)

    @classmethod
    def start_node_thread(cls) -> None:
        # NOTE: Implement thread startup
        pass

    @classmethod
    def execute_dag_workflow(cls) -> tuple[ExecutionResult, list[str]]:
        """Execute the DAG workflow using topological sorting approach.

        Based on the provided pseudocode but without threading implementation yet.

        Returns:
            Tuple of (ExecutionResult, error_list)
        """
        # Initialize workflow state
        workflow_state = WorkflowState.NO_ERROR
        node_states: dict[str, NodeState] = {}
        thread_pool = ThreadPoolExecutor(max_workers=3)
        error_list: list[str] = []

        # Mark all nodes as QUEUED initially
        for node in cls.network.nodes():
            node_states[node] = NodeState.QUEUED

        while workflow_state == WorkflowState.NO_ERROR:
            # Find leaf nodes not in canceled state using topological approach
            remaining_graph = cls.network

            # Remove nodes that are DONE, CANCELED, or PROCESSING
            nodes_to_remove = [
                node
                for node, state in node_states.items()
                if state in [NodeState.DONE, NodeState.CANCELED, NodeState.PROCESSING]
            ]
            remaining_graph.remove_nodes_from(nodes_to_remove)

            # Get ready nodes (leaf nodes with in_degree = 0 in remaining graph)
            ready_nodes = [
                node
                for node in remaining_graph.nodes()
                if dict(remaining_graph.in_degree())[node] == 0 and node_states[node] == NodeState.QUEUED
            ]

            if not ready_nodes:
                workflow_state = WorkflowState.WORKFLOW_COMPLETE
                break

            # Check if any nodes are in DONE state (completed since last iteration)
            done_nodes = [node for node, state in node_states.items() if state == NodeState.DONE]
            if done_nodes:
                # Remove edges from completed nodes (pop from graph)
                for done_node in done_nodes:
                    cls.network.remove_node(done_node)
                continue

            # NOTE: Threading implementation will go here later
            # Future: Check for available threads and allocate to ready nodes

            # For now, just process nodes sequentially without threading
            for node in ready_nodes:
                node_states[node] = NodeState.PROCESSING
                # NOTE: Actual node execution will be implemented here
                # For now, mark as done immediately
                node_states[node] = NodeState.DONE

        # Handle final workflow state
        if workflow_state == WorkflowState.WORKFLOW_COMPLETE:
            if any(state == NodeState.ERRORED for state in node_states.values()):
                return ExecutionResult.ERRORED, error_list
            return ExecutionResult.COMPLETED_SUCCESSFULLY, []
        return ExecutionResult.ERRORED, error_list

    @classmethod
    def on_node_complete(cls, _node: str, _node_states: dict[str, NodeState]) -> None:
        """Callback for when a node completes successfully.

        NOTE: Will be used with threading implementation.
        """

    @classmethod
    def on_node_error(
        cls, _node: str, _error: str, _node_states: dict[str, NodeState], _error_list: list[str]
    ) -> WorkflowState:
        """Callback for when a node encounters an error.

        NOTE: Will be used with threading implementation.
        """
        return WorkflowState.ERRORED

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
