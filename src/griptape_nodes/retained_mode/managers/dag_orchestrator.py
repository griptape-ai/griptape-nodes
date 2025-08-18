from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

import networkx as nx

from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from concurrent.futures import Future

    from griptape_nodes.exe_types.node_types import BaseNode


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
    def draw(cls) -> None:
        """Draw the network graph. For testing and visualization purposes."""
        nx.draw(cls.network, with_labels=True)
        topo_order_line_graph = list(nx.topological_sort(nx.line_graph(cls.network)))
        topo_order = list(nx.topological_sort(cls.network))
        topo_generations = list(nx.topological_generations(cls.network))

        from griptape_nodes.retained_mode.griptape_nodes import logger

        logger.info(f"Topological Line Graph order: {topo_order_line_graph}")
        logger.info(f"Topological order: {topo_order}")
        logger.info(f"Topological generations: {topo_generations}")

    @classmethod
    def get_node_queue(cls) -> list[str]:
        # NOTE: Implement node queue retrieval
        return []

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
        # NOTE: thread_pool = ThreadPool() - will implement threading later
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
    def run_orchestrator(cls) -> None:
        """Legacy method - replaced by execute_dag_workflow.

        NOTE: Remove or refactor to use execute_dag_workflow.
        """
