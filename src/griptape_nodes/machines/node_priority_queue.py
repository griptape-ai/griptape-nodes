"""Priority queue for managing node execution order."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode
    from griptape_nodes.machines.parallel_resolution import ParallelResolutionContext


class NodeHeuristic(ABC):
    """Base class for node priority heuristics."""

    def __init__(self, context: ParallelResolutionContext, weight: float = 1, max_value: float = 100.0) -> None:
        self._context = context
        # The weight of this specific heuristic. Higher weight means higher priority, assuming the maximum values are the same (otherwise weight will have less of an effect)
        self._weight = weight
        # This is the value we use to get the maximum value that we want to allow to be set for a heuristic.
        self.max_value = max_value

    @property
    def weight(self) -> float:
        return self._weight

    @weight.setter
    def weight(self, value: float) -> None:
        self._weight = value

    @abstractmethod
    def calculate_priority(self, dag_node: DagNode, **kwargs) -> float:
        pass

    @abstractmethod
    def calculate_priorities_batch(self, dag_nodes: list[DagNode], **kwargs) -> dict[str, float]:
        """Calculate priorities for multiple nodes at once.

        Default implementation calls calculate_priority for each node.
        Subclasses can override for better performance.

        Args:
            dag_nodes: List of nodes to calculate priorities for
            **kwargs: Additional arguments passed to calculate_priority

        Returns:
            Dictionary mapping node names to priority scores
        """


class DistanceToNode(NodeHeuristic):
    """Prioritize nodes based on their spatial proximity to the previously executed node.

    This heuristic assigns higher priority to nodes that are closer to the last executed node
    in the visual canvas. Distance is calculated using squared Euclidean distance for efficiency.

    Scoring:
    - Nodes closer to the previous node receive higher scores (approaching max_value)
    - Nodes farther away receive lower scores (approaching 1.0)
    - When no previous node exists, all nodes receive a neutral score (max_value/2)
    - Distances are normalized across all available nodes to ensure consistent scoring

    This encourages execution flow that follows the visual layout of the workflow.
    """

    def calculate_priority(self, dag_node: DagNode, **kwargs) -> float:
        previous_executed_node = kwargs.get("previous_executed_node")
        if previous_executed_node is None:
            return self.max_value / 2

        current_pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
        prev_pos = previous_executed_node.node_reference.metadata.get("position", {"x": 0, "y": 0})

        distance_squared = (current_pos["x"] - prev_pos["x"]) ** 2 + (current_pos["y"] - prev_pos["y"]) ** 2

        all_distances_squared = []
        for node_ref in self._context.node_to_reference.values():
            pos = node_ref.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d_squared = (pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2
            all_distances_squared.append(d_squared)

        if not all_distances_squared or len(all_distances_squared) == 1:
            return self.max_value / 2

        min_distance_squared = min(all_distances_squared)
        max_distance_squared = max(all_distances_squared)

        if max_distance_squared == min_distance_squared:
            return self.max_value / 2

        normalized = (distance_squared - min_distance_squared) / (max_distance_squared - min_distance_squared)
        return self.max_value - (normalized * 99.0)

    def calculate_priorities_batch(self, dag_nodes: list[DagNode], **kwargs) -> dict[str, float]:
        previous_executed_node = kwargs.get("previous_executed_node")
        if previous_executed_node is None:
            return {node.node_reference.name: self.max_value / 2 for node in dag_nodes}

        if not dag_nodes:
            return {}

        if len(dag_nodes) == 1:
            return {dag_nodes[0].node_reference.name: self.max_value / 2}

        prev_pos = previous_executed_node.node_reference.metadata.get("position", {"x": 0, "y": 0})

        distances_squared = []
        for dag_node in dag_nodes:
            pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d_squared = (pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2
            distances_squared.append((dag_node, d_squared))

        min_distance_squared = min(d for _, d in distances_squared)
        max_distance_squared = max(d for _, d in distances_squared)

        results = {}
        for dag_node, distance_squared in distances_squared:
            if max_distance_squared == min_distance_squared:
                score = self.max_value / 2
            else:
                normalized = (distance_squared - min_distance_squared) / (max_distance_squared - min_distance_squared)
                score = self.max_value - (normalized * 99.0)

            results[dag_node.node_reference.name] = score

        return results


class TopLeftToBottomRight(NodeHeuristic):
    """Prioritize nodes based on top-left to bottom-right reading order.

    This heuristic assigns higher priority to nodes positioned earlier in a natural
    reading flow (top-left of the canvas) and lower priority to nodes positioned
    later (bottom-right).

    Scoring:
    - Reading order is calculated as: y_position + x_position
    - Nodes with smaller reading order values (top-left) receive higher scores
    - Nodes with larger reading order values (bottom-right) receive lower scores
    - Scores are normalized across all nodes to ensure consistent priority distribution

    This creates a predictable execution pattern that follows visual layout conventions,
    making workflow execution more intuitive for users.
    """

    def calculate_priority(self, dag_node: DagNode, **kwargs) -> float:  # noqa: ARG002
        current_pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
        current_reading_order = current_pos["y"] + current_pos["x"]

        all_reading_orders = []
        for node_ref in self._context.node_to_reference.values():
            pos = node_ref.node_reference.metadata.get("position", {"x": 0, "y": 0})
            reading_order = pos["y"] + pos["x"]
            all_reading_orders.append(reading_order)

        if not all_reading_orders or len(all_reading_orders) == 1:
            return self.max_value / 2

        min_reading_order = min(all_reading_orders)
        max_reading_order = max(all_reading_orders)

        if max_reading_order == min_reading_order:
            return self.max_value / 2

        normalized = (current_reading_order - min_reading_order) / (max_reading_order - min_reading_order)
        return self.max_value - (normalized * 99.0)

    def calculate_priorities_batch(self, dag_nodes: list[DagNode], **kwargs) -> dict[str, float]:  # noqa: ARG002
        if not dag_nodes:
            return {}

        if len(dag_nodes) == 1:
            return {dag_nodes[0].node_reference.name: self.max_value / 2}

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
                score = self.max_value / 2
            else:
                normalized = (reading_order - min_reading_order) / (max_reading_order - min_reading_order)
                score = self.max_value - (normalized * 99.0)

            results[dag_node.node_reference.name] = score

        return results


class HasConnectionFromPrevious(NodeHeuristic):
    """Prioritize nodes that are direct successors of the previously executed node.

    This heuristic gives maximum priority to nodes that have a direct connection from
    the last resolved node, encouraging execution to follow the natural flow of data
    and control through the workflow graph.

    Scoring:
    - Nodes that are direct successors of the previous node receive max_value
    - All other nodes receive a score of 0.0
    - When no previous node exists, all nodes receive 0.0

    This creates strong preference for following explicit connection paths, which helps
    maintain data locality and reduces context switching during parallel execution.
    """

    def calculate_priority(self, dag_node: DagNode, **kwargs) -> float:
        previous_executed_node = kwargs.get("previous_executed_node")
        last_resolved_successors = kwargs.get("last_resolved_successors", set())

        if previous_executed_node is None:
            return 0.0

        current_node_name = dag_node.node_reference.name

        # Check if current node was a successor of the last resolved node
        if current_node_name in last_resolved_successors:
            return self.max_value

        return 0.0

    def calculate_priorities_batch(self, dag_nodes: list[DagNode], **kwargs) -> dict[str, float]:
        previous_executed_node = kwargs.get("previous_executed_node")
        last_resolved_successors = kwargs.get("last_resolved_successors", set())

        if previous_executed_node is None:
            return {node.node_reference.name: 0.0 for node in dag_nodes}

        if not dag_nodes:
            return {}

        results = {}
        for dag_node in dag_nodes:
            if dag_node.node_reference.name in last_resolved_successors:
                results[dag_node.node_reference.name] = self.max_value
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
        self._last_resolved_successors: set[str] = set()  # Nodes connected to last resolved node
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

        if len(self._queued_nodes) == 1:
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
            scores = heuristic.calculate_priorities_batch(
                dag_nodes,
                previous_executed_node=previous_executed_node,
                last_resolved_successors=self._last_resolved_successors,
            )

            for node_name, score in scores.items():
                combined_priorities[node_name] += score * heuristic.weight

        # Sort the string names directly
        self._queued_nodes.sort(key=lambda name: combined_priorities[name], reverse=True)
