from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

    from griptape_nodes.exe_types.node_types import BaseNode

from griptape_nodes.machines.fsm import State

logger = logging.getLogger("griptape_nodes")


# Directed Acyclic Graph
class DAG:
    """Directed Acyclic Graph for tracking node dependencies during resolution."""

    def __init__(self) -> None:
        """Initialize the DAG with empty graph and in-degree structures."""
        self.graph = defaultdict(set)  # adjacency list
        self.in_degree = defaultdict(int)  # number of unmet dependencies

    def add_node(self, node: BaseNode) -> None:
        """Ensure the node exists in the graph."""
        self.graph[node]

    def add_edge(self, from_node: BaseNode, to_node: BaseNode) -> None:
        """Add a directed edge from 'from_node' to 'to_node'."""
        self.graph[from_node].add(to_node)
        self.in_degree[to_node] += 1

    def get_ready_nodes(self) -> list[BaseNode]:
        """Return nodes with no unmet dependencies (in-degree 0)."""
        return [node for node in self.graph if self.in_degree[node] == 0]

    def mark_processed(self, node: BaseNode) -> None:
        """Mark a node as processed, decrementing in-degree of its dependents."""
        # Remove outgoing edges from this node
        for dependent in self.graph[node]:
            self.in_degree[dependent] -= 1
        self.graph.pop(node, None)
        self.in_degree.pop(node, None)

    def get_all_nodes(self) -> list[BaseNode]:
        """Return a list of all nodes currently in the DAG."""
        return list(self.graph.keys())


@dataclass
class Focus:
    """Represents a node currently being resolved, with optional scheduled value and generator."""

    node: BaseNode
    scheduled_value: Any | None = None
    updated: bool = True
    process_generator: Generator | None = None


# This is on a per-node basis
class ResolutionContext:
    """Context for node resolution, including the focus stack, DAG, and paused state."""

    root_node_resolving: BaseNode | None
    current_focuses: list[Focus]
    paused: bool
    DAG: DAG

    def __init__(self) -> None:
        """Initialize the resolution context with empty DAG."""
        self.paused = False
        self.DAG = DAG()
        self.current_focuses = []
        self.root_node_resolving = None

    def reset(self) -> None:
        """Reset the DAG, and paused state."""
        if self.DAG is not None:
            for node in self.DAG.graph:
                node.clear_node()
            self.DAG.graph.clear()
            self.DAG.in_degree.clear()
        self.paused = False


class CompleteState(State):
    """State indicating node resolution is complete."""

    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        """Enter the CompleteState."""
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        """Update the CompleteState (no-op)."""
        return None
