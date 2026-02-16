"""Connection-based node priority heuristic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.machines.heuristics.base_heuristic import NodeHeuristic

if TYPE_CHECKING:
    from griptape_nodes.machines.dag_builder import DagNode


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
