"""Priority queue for managing node execution order."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionContext


class NodeHeuristic(ABC):
    """Base class for node priority heuristics."""

    def __init__(self, context: ParallelResolutionContext, weight: float = 1) -> None:
        self._context = context
        self._weight = weight

    @property
    def weight(self) -> float:
        return self._weight

    @weight.setter
    def weight(self, value: float) -> None:
        self._weight = value

    @abstractmethod
    def calculate_priority(self, dag_node: DagNode, *args) -> float:
        pass

    def calculate_priorities_batch(self, dag_nodes: list[DagNode], *args) -> dict[str, float]:
        """Calculate priorities for multiple nodes at once.

        Default implementation calls calculate_priority for each node.
        Subclasses can override for better performance.

        Args:
            dag_nodes: List of nodes to calculate priorities for
            *args: Additional arguments passed to calculate_priority

        Returns:
            Dictionary mapping node names to priority scores
        """
        return {node.node_reference.name: self.calculate_priority(node, *args) for node in dag_nodes}


class DistanceToNode(NodeHeuristic):
    def calculate_priority(self, dag_node: DagNode, previous_executed_node: DagNode | None) -> float:
        if previous_executed_node is None:
            return 50.0 * self._weight

        current_pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
        prev_pos = previous_executed_node.node_reference.metadata.get("position", {"x": 0, "y": 0})

        distance = ((current_pos["x"] - prev_pos["x"]) ** 2 + (current_pos["y"] - prev_pos["y"]) ** 2) ** 0.5

        all_distances = []
        for node_ref in self._context.node_to_reference.values():
            pos = node_ref.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d = ((pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2) ** 0.5
            all_distances.append(d)

        if not all_distances or len(all_distances) == 1:
            return 50.0 * self._weight

        min_distance = min(all_distances)
        max_distance = max(all_distances)

        if max_distance == min_distance:
            score = 50.0
        else:
            normalized = (distance - min_distance) / (max_distance - min_distance)
            score = 100.0 - (normalized * 99.0)

        return score * self._weight

    def calculate_priorities_batch(
        self, dag_nodes: list[DagNode], previous_executed_node: DagNode | None
    ) -> dict[str, float]:
        if previous_executed_node is None:
            return {node.node_reference.name: 50.0 * self._weight for node in dag_nodes}

        if not dag_nodes:
            return {}

        if len(dag_nodes) == 1:
            return {dag_nodes[0].node_reference.name: 50.0 * self._weight}

        prev_pos = previous_executed_node.node_reference.metadata.get("position", {"x": 0, "y": 0})

        distances = []
        for dag_node in dag_nodes:
            pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d = ((pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2) ** 0.5
            distances.append((dag_node, d))

        min_distance = min(d for _, d in distances)
        max_distance = max(d for _, d in distances)

        results = {}
        for dag_node, distance in distances:
            if max_distance == min_distance:
                score = 50.0
            else:
                normalized = (distance - min_distance) / (max_distance - min_distance)
                score = 100.0 - (normalized * 99.0)

            results[dag_node.node_reference.name] = score * self._weight

        return results


class TopLeftToBottomRight(NodeHeuristic):
    def calculate_priority(self, dag_node: DagNode) -> float:
        current_pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
        current_reading_order = current_pos["y"] + current_pos["x"]

        all_reading_orders = []
        for node_ref in self._context.node_to_reference.values():
            pos = node_ref.node_reference.metadata.get("position", {"x": 0, "y": 0})
            reading_order = pos["y"] + pos["x"]
            all_reading_orders.append(reading_order)

        if not all_reading_orders or len(all_reading_orders) == 1:
            return 50.0 * self._weight

        min_reading_order = min(all_reading_orders)
        max_reading_order = max(all_reading_orders)

        if max_reading_order == min_reading_order:
            score = 50.0
        else:
            normalized = (current_reading_order - min_reading_order) / (max_reading_order - min_reading_order)
            score = 100.0 - (normalized * 99.0)

        return score * self._weight

    def calculate_priorities_batch(self, dag_nodes: list[DagNode]) -> dict[str, float]:
        if not dag_nodes:
            return {}

        if len(dag_nodes) == 1:
            return {dag_nodes[0].node_reference.name: 50.0 * self._weight}

        reading_orders = []
        for dag_node in dag_nodes:
            pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
            reading_order = pos["y"] + pos["x"]
            reading_orders.append((dag_node, reading_order))

        min_reading_order = min(ro for _, ro in reading_orders)
        max_reading_order = max(ro for _, ro in reading_orders)

        results = {}
        for dag_node, reading_order in reading_orders:
            if max_reading_order == min_reading_order:
                score = 50.0
            else:
                normalized = (reading_order - min_reading_order) / (max_reading_order - min_reading_order)
                score = 100.0 - (normalized * 99.0)

            results[dag_node.node_reference.name] = score * self._weight

        return results


class HasConnectionFromPrevious(NodeHeuristic):
    def calculate_priority(self, dag_node: DagNode, previous_executed_node: DagNode | None) -> float:
        if previous_executed_node is None:
            return 0.0

        prev_node_name = previous_executed_node.node_reference.name
        current_node_name = dag_node.node_reference.name

        if self._context.dag_builder is None:
            return 0.0

        for graph in self._context.dag_builder.graphs.values():
            if current_node_name in graph._predecessors and prev_node_name in graph._predecessors[current_node_name]:
                return 100.0 * self._weight

        return 0.0

    def calculate_priorities_batch(
        self, dag_nodes: list[DagNode], previous_executed_node: DagNode | None
    ) -> dict[str, float]:
        if previous_executed_node is None:
            return {node.node_reference.name: 0.0 for node in dag_nodes}

        if not dag_nodes:
            return {}

        if self._context.dag_builder is None:
            return {node.node_reference.name: 0.0 for node in dag_nodes}

        prev_node_name = previous_executed_node.node_reference.name

        connected_nodes = set()
        for graph in self._context.dag_builder.graphs.values():
            for node_name in graph._predecessors:
                if prev_node_name in graph._predecessors[node_name]:
                    connected_nodes.add(node_name)

        results = {}
        for dag_node in dag_nodes:
            if dag_node.node_reference.name in connected_nodes:
                results[dag_node.node_reference.name] = 100.0 * self._weight
            else:
                results[dag_node.node_reference.name] = 0.0

        return results


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
        self._needs_reorder = False  # Lazy reorder flag
        self._heuristics: list[NodeHeuristic] = [
            HasConnectionFromPrevious(context, weight=1.0),
            DistanceToNode(context, weight=1.0),
            TopLeftToBottomRight(context, weight=1.0),
        ]

    def add_node(self, dag_node: DagNode) -> str:
        """Add a node to the priority queue and mark for reordering.

        Args:
            dag_node: The DagNode to add to the queue

        Returns:
            The name of the node that was added
        """
        node_name = dag_node.node_reference.name
        if node_name not in self._queued_nodes:
            self._queued_nodes.append(node_name)
            self._needs_reorder = True
        return node_name

    def get_next_node(self) -> str | None:
        """Get and remove the highest priority node from the queue.

        Returns:
            The name of the highest priority node, or None if queue is empty
        """
        if self._needs_reorder:
            self._reorder()
            self._needs_reorder = False

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

    def mark_priorities_stale(self) -> None:
        """Mark priorities as needing recalculation.

        Called when context.last_resolved_node changes and existing
        queued nodes need reprioritization based on the new context.
        """
        if self._queued_nodes:
            self._needs_reorder = True

    def _reorder(self) -> None:
        """Reorder the queue based on current node priorities."""
        if not self._queued_nodes:
            return

        # Look up DagNodes from context only during reorder
        dag_nodes = [self._context.node_to_reference[name] for name in self._queued_nodes]

        previous_executed_node = None
        if self._context.last_resolved_node is not None:
            node_name = self._context.last_resolved_node.name
            if node_name in self._context.node_to_reference:
                previous_executed_node = self._context.node_to_reference[node_name]

        combined_priorities: dict[str, float] = {node.node_reference.name: 0.0 for node in dag_nodes}

        for heuristic in self._heuristics:
            if isinstance(heuristic, (DistanceToNode, HasConnectionFromPrevious)):
                scores = heuristic.calculate_priorities_batch(dag_nodes, previous_executed_node)
            else:
                scores = heuristic.calculate_priorities_batch(dag_nodes)

            for node_name, score in scores.items():
                combined_priorities[node_name] += score

        # Sort the string names directly
        self._queued_nodes.sort(key=lambda name: combined_priorities[name], reverse=True)
