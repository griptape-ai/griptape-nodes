"""Reading order-based node priority heuristic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.machines.heuristics.base_heuristic import NodeHeuristic

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode


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
