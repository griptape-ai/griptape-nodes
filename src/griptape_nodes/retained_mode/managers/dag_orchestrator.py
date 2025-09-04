from __future__ import annotations

import asyncio
import graphlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class DirectedGraph:
    """Directed graph implementation using Python's graphlib for DAG operations."""

    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._predecessors: dict[str, set[str]] = {}

    def add_node(self, node_for_adding: str) -> None:
        """Add a node to the graph."""
        self._nodes.add(node_for_adding)
        if node_for_adding not in self._predecessors:
            self._predecessors[node_for_adding] = set()

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a directed edge from from_node to to_node."""
        self.add_node(from_node)
        self.add_node(to_node)
        self._predecessors[to_node].add(from_node)

    def nodes(self) -> set[str]:
        """Return all nodes in the graph."""
        return self._nodes.copy()

    def in_degree(self, node: str) -> int:
        """Return the in-degree of a node (number of incoming edges)."""
        if node not in self._nodes:
            return 0
        return len(self._predecessors.get(node, set()))

    def remove_node(self, node: str) -> None:
        """Remove a node and all its edges from the graph."""
        if node not in self._nodes:
            return

        self._nodes.remove(node)

        # Remove this node from all predecessor lists
        for predecessors in self._predecessors.values():
            predecessors.discard(node)

        # Remove this node's predecessor entry
        if node in self._predecessors:
            del self._predecessors[node]

    def clear(self) -> None:
        """Clear all nodes and edges from the graph."""
        self._nodes.clear()
        self._predecessors.clear()

    def get_topological_sorter(self) -> graphlib.TopologicalSorter[str]:
        """Create a TopologicalSorter from the current graph structure."""
        return graphlib.TopologicalSorter(self._predecessors)


class NodeState(StrEnum):
    """Individual node execution states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    ERRORED = "errored"
    WAITING = "waiting"


# orchestrator attached to each flow, owned by griptape nodes
class DagOrchestrator:
    """Main DAG structure containing nodes and edges for a specific flow."""

    # The generated network of nodes
    network: DirectedGraph
    # The node to reference mapping. Includes node and thread references.
    node_to_reference: dict[str, DagOrchestrator.DagNode]
    # Async execution support
    async_semaphore: asyncio.Semaphore
    task_to_node: dict[asyncio.Task, DagOrchestrator.DagNode]
    # The flow this orchestrator is associated with
    flow_name: str

    def __init__(self, flow_name: str, max_workers: int | None = None) -> None:
        """Initialize a DagOrchestrator for a specific flow.

        Args:
            flow_name: The name of the flow this orchestrator manages
            max_workers: Maximum number of worker threads (defaults to ThreadPoolExecutor default)
        """
        self.flow_name = flow_name
        self.network = DirectedGraph()
        # Node to reference will also contain node state.
        self.node_to_reference = {}
        # Prevents a worker queue from developing
        # Async execution setup
        max_workers = max_workers if max_workers is not None else 5
        self.async_semaphore = asyncio.Semaphore(max_workers)
        self.task_to_node = {}

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        task_reference: asyncio.Task | None = field(default=None)
        node_state: NodeState = field(default=NodeState.WAITING)
        node_reference: BaseNode

    def clear(self) -> None:
        """Clear the DAG state but keep the thread pool alive for reuse."""
        self.network.clear()
        self.node_to_reference.clear()
        self.task_to_node.clear()
