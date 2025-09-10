from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.common.directed_graph import DirectedGraph

if TYPE_CHECKING:
    import asyncio

    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class NodeState(StrEnum):
    """Individual node execution states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    ERRORED = "errored"
    WAITING = "waiting"


@dataclass(kw_only=True)
class DagNode:
    """Represents a node in the DAG with runtime references."""

    task_reference: asyncio.Task | None = field(default=None)
    node_state: NodeState = field(default=NodeState.WAITING)
    node_reference: BaseNode


class DagBuilder:
    """Handles DAG construction independently of execution state machine."""

    def __init__(self) -> None:
        self.graph = DirectedGraph()
        self.node_to_reference: dict[str, DagNode] = {}

    def add_node_with_dependencies(self, node: BaseNode) -> list[BaseNode]:
        """Add node and all its dependencies to DAG. Returns list of added nodes."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        added_nodes = []

        def _add_node_recursive(current_node: BaseNode, visited: set[str]) -> None:
            if current_node.name in visited:
                return
            visited.add(current_node.name)

            # Skip if already in DAG (use DAG membership, not resolved state)
            if current_node.name in self.node_to_reference:
                return

            # Process dependencies first (depth-first)
            for param in current_node.parameters:
                upstream_connection = connections.get_connected_node(current_node, param)
                if upstream_connection:
                    upstream_node, _ = upstream_connection

                    # If upstream is already in DAG, just add edge
                    if upstream_node.name in self.node_to_reference:
                        self.graph.add_edge(upstream_node.name, current_node.name)
                    # Otherwise, add it to DAG first
                    else:
                        _add_node_recursive(upstream_node, visited)
                        self.graph.add_edge(upstream_node.name, current_node.name)

            # Add current node to DAG (but keep original resolution state)

            dag_node = DagNode(node_reference=current_node, node_state=NodeState.WAITING)
            self.node_to_reference[current_node.name] = dag_node
            self.graph.add_node(node_for_adding=current_node.name)
            # DON'T mark as resolved - that happens during actual execution
            added_nodes.append(current_node)

        _add_node_recursive(node, set())
        return added_nodes

    def add_node(self, node: BaseNode) -> DagNode:
        """Add just one node to DAG without dependencies (assumes dependencies already exist)."""
        if node.name in self.node_to_reference:
            return self.node_to_reference[node.name]

        dag_node = DagNode(node_reference=node, node_state=NodeState.WAITING)
        self.node_to_reference[node.name] = dag_node
        self.graph.add_node(node_for_adding=node.name)
        return dag_node

    def clear(self) -> None:
        """Clear all nodes and references from the DAG builder."""
        self.graph.clear()
        self.node_to_reference.clear()
