"""Distance-based node priority heuristic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.machines.heuristics.base_heuristic import NodeHeuristic

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode


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

        # Track min/max distances in a single pass
        min_distance_squared = float("inf")
        max_distance_squared = 0.0
        node_count = 0
        for node_ref in self._context.node_to_reference.values():
            pos = node_ref.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d_squared = (pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2
            min_distance_squared = min(min_distance_squared, d_squared)
            max_distance_squared = max(max_distance_squared, d_squared)
            node_count += 1

        if node_count in {0, 1}:
            return self.max_value / 2

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

        # Track min/max while building the list to avoid additional passes
        distances_squared = []
        min_distance_squared = float("inf")
        max_distance_squared = 0.0
        for dag_node in dag_nodes:
            pos = dag_node.node_reference.metadata.get("position", {"x": 0, "y": 0})
            d_squared = (pos["x"] - prev_pos["x"]) ** 2 + (pos["y"] - prev_pos["y"]) ** 2
            distances_squared.append((dag_node, d_squared))
            min_distance_squared = min(min_distance_squared, d_squared)
            max_distance_squared = max(max_distance_squared, d_squared)

        results = {}
        for dag_node, distance_squared in distances_squared:
            if max_distance_squared == min_distance_squared:
                score = self.max_value / 2
            else:
                normalized = (distance_squared - min_distance_squared) / (max_distance_squared - min_distance_squared)
                score = self.max_value - (normalized * 99.0)

            results[dag_node.node_reference.name] = score

        return results
