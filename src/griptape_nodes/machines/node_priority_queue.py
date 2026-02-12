"""Priority queue for managing node execution order."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionContext


class NodePriorityQueue:
    """Manages priority-based ordering of nodes ready for execution.

    This is a simple framework that stores nodes and returns them in priority order.
    The _calculate_priority() method is the extension point for future heuristics.
    """

    def __init__(self, context: ParallelResolutionContext) -> None:
        """Initialize the priority queue.

        Args:
            context: The execution context containing node references and DAG state
        """
        self._context = context
        self._queued_nodes: list[str] = []  # Node names, sorted by priority (highest first)

    def add_node(self, node_name: str) -> None:
        """Add a node to the priority queue and reorder.

        Args:
            node_name: Name of the node to add
        """
        if node_name not in self._queued_nodes:
            self._queued_nodes.append(node_name)
            self._reorder()

    def get_next_node(self) -> str | None:
        """Get and remove the highest priority node from the queue.

        Returns:
            The name of the highest priority node, or None if queue is empty
        """
        if self._queued_nodes:
            return self._queued_nodes.pop(0)
        return None

    def remove_node(self, node_name: str) -> None:
        """Remove a node from the priority queue.

        Args:
            node_name: Name of the node to remove
        """
        if node_name in self._queued_nodes:
            self._queued_nodes.remove(node_name)

    def update_on_node_complete(self, node_name: str) -> None:
        """Called when a node completes execution.

        Triggers reordering so priorities can be recalculated.

        Args:
            node_name: Name of the node that just completed
        """
        self._reorder()

    def _reorder(self) -> None:
        """Reorder the queue based on current node priorities."""
        if not self._queued_nodes:
            return

        # Calculate priority for each node
        nodes_with_priority = []
        for node_name in self._queued_nodes:
            dag_node = self._context.node_to_reference[node_name]
            priority = self._calculate_priority(dag_node)
            nodes_with_priority.append((node_name, priority))

        # Sort by priority (highest first)
        nodes_with_priority.sort(key=lambda x: x[1], reverse=True)

        # Update the queued nodes list
        self._queued_nodes = [node_name for node_name, _ in nodes_with_priority]

    def _calculate_priority(self, dag_node: DagNode) -> float:
        """Calculate priority for a node.

        Extension point for future heuristics.
        Currently returns 0.0 for all nodes (FIFO behavior).

        Args:
            dag_node: The node to calculate priority for

        Returns:
            Priority value (higher values = higher priority)
        """
        return 0.0
