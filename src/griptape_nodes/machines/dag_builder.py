from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.common.directed_graph import DirectedGraph
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import LOCAL_EXECUTION, NodeGroupNode, NodeResolutionState

if TYPE_CHECKING:
    import asyncio

    from griptape_nodes.exe_types.connections import Connections
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

    graphs: dict[str, DirectedGraph]  # Str is the name of the start node associated here.
    node_to_reference: dict[str, DagNode]
    graph_to_nodes: dict[str, set[str]]  # Track which nodes belong to which graph

    def __init__(self) -> None:
        self.graphs = {}
        self.node_to_reference: dict[str, DagNode] = {}
        self.graph_to_nodes = {}

    @staticmethod
    def _should_use_parent_group(node: BaseNode) -> bool:
        """Check if a node's parent group should be used for DAG edges.

        Returns True if the node has a parent NodeGroupNode that is NOT in LOCAL_EXECUTION mode.
        In LOCAL_EXECUTION mode, groups are transparent and children are treated as separate nodes.
        """
        if not isinstance(node.parent_group, NodeGroupNode):
            return False
        parent_execution_env = node.parent_group.get_parameter_value(node.parent_group.execution_environment.name)
        return parent_execution_env != LOCAL_EXECUTION

    def _get_node_for_dag_edge(self, node: BaseNode, graph: DirectedGraph, graph_name: str) -> BaseNode:
        """Get the node to use for DAG edges - either the node itself or its parent group.

        Args:
            node: The original node
            graph: The graph being built
            graph_name: Name of the graph for tracking

        Returns:
            The node or parent group to use in DAG edges
        """
        if self._should_use_parent_group(node):
            parent_group = node.parent_group
            if isinstance(parent_group, NodeGroupNode):
                self._ensure_group_node_in_dag(parent_group, graph, graph_name)
                return parent_group
        return node

    def _ensure_group_node_in_dag(self, group_node: NodeGroupNode, graph: DirectedGraph, graph_name: str) -> None:
        """Ensure a NodeGroupNode is added to the DAG if not already present.

        Args:
            group_node: The NodeGroupNode to add
            graph: The graph to add it to
            graph_name: Name of the graph for tracking
        """
        if group_node.name not in self.node_to_reference:
            dag_node = DagNode(node_reference=group_node, node_state=NodeState.WAITING)
            self.node_to_reference[group_node.name] = dag_node
            graph.add_node(node_for_adding=group_node.name)
            self.graph_to_nodes[graph_name].add(group_node.name)

    # Complex with the inner recursive method, but it needs connections and added_nodes.
    def add_node_with_dependencies(self, node: BaseNode, graph_name: str = "default") -> list[BaseNode]:  # noqa: C901
        """Add node and all its dependencies to DAG. Returns list of added nodes."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        added_nodes = []
        graph = self.graphs.get(graph_name, None)
        if graph is None:
            graph = DirectedGraph()
            self.graphs[graph_name] = graph
            self.graph_to_nodes[graph_name] = set()

        def _add_node_recursive(current_node: BaseNode, visited: set[str], graph: DirectedGraph) -> None:
            # Skip if already visited or already in DAG
            if current_node.name in visited:
                return
            visited.add(current_node.name)

            if current_node.name in self.node_to_reference:
                return

            # Check if we should ignore dependencies (for special nodes like output_selector)
            ignore_data_dependencies = hasattr(current_node, "ignore_dependencies")

            # Process all upstream dependencies first (depth-first traversal)
            for param in current_node.parameters:
                # Skip control flow parameters
                if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                    continue

                # Skip if node ignores dependencies
                if ignore_data_dependencies:
                    continue

                upstream_connection = connections.get_connected_node(current_node, param)
                if not upstream_connection:
                    continue

                upstream_node, _ = upstream_connection

                # Skip already resolved nodes
                if upstream_node.state == NodeResolutionState.RESOLVED:
                    continue

                # Check for internal group connections - traverse but don't add edge
                is_internal_connection = (
                    self._should_use_parent_group(current_node)
                    and upstream_node.parent_group == current_node.parent_group
                )

                # Recursively add upstream node
                _add_node_recursive(upstream_node, visited, graph)

                # Add edge unless it's an internal group connection
                if not is_internal_connection:
                    upstream_for_edge = self._get_node_for_dag_edge(upstream_node, graph, graph_name)
                    current_for_edge = self._get_node_for_dag_edge(current_node, graph, graph_name)
                    graph.add_edge(upstream_for_edge.name, current_for_edge.name)

            # Always add current node to tracking (even if parent group is used for edges)
            dag_node = DagNode(node_reference=current_node, node_state=NodeState.WAITING)
            self.node_to_reference[current_node.name] = dag_node
            added_nodes.append(current_node)

            # Add to graph if not using parent group
            if not self._should_use_parent_group(current_node):
                graph.add_node(node_for_adding=current_node.name)
                self.graph_to_nodes[graph_name].add(current_node.name)

        _add_node_recursive(node, set(), graph)

        return added_nodes

    def add_node(self, node: BaseNode, graph_name: str = "default") -> DagNode:
        """Add just one node to DAG without dependencies (assumes dependencies already exist)."""
        if node.name in self.node_to_reference:
            return self.node_to_reference[node.name]

        dag_node = DagNode(node_reference=node, node_state=NodeState.WAITING)
        self.node_to_reference[node.name] = dag_node
        graph = self.graphs.get(graph_name, None)
        if graph is None:
            graph = DirectedGraph()
            self.graphs[graph_name] = graph
        graph.add_node(node_for_adding=node.name)

        # Track which nodes belong to this graph
        if graph_name not in self.graph_to_nodes:
            self.graph_to_nodes[graph_name] = set()
        self.graph_to_nodes[graph_name].add(node.name)

        return dag_node

    def clear(self) -> None:
        """Clear all nodes and references from the DAG builder."""
        self.graphs.clear()
        self.node_to_reference.clear()
        self.graph_to_nodes.clear()

    def can_queue_control_node(self, node: DagNode) -> bool:
        if len(self.graphs) == 1:
            return True

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        control_connections = self.get_number_incoming_control_connections(node.node_reference, connections)
        if control_connections <= 1:
            return True

        for graph in self.graphs.values():
            # If the length of the graph is 0, skip it. it's either reached it or it's a dead end.
            if len(graph.nodes()) == 0:
                continue

            # If graph has nodes, the root node (not the leaf, the root), check forward path from that
            root_nodes = [n for n in graph.nodes() if graph.out_degree(n) == 0]
            for root_node_name in root_nodes:
                if root_node_name in self.node_to_reference:
                    root_node = self.node_to_reference[root_node_name].node_reference

                    # Skip if the root node is the same as the target node - it can't reach itself
                    if root_node == node.node_reference:
                        continue

                    # Check if the target node is in the forward path from this root
                    if self._is_node_in_forward_path(root_node, node.node_reference, connections):
                        return False  # This graph could still reach the target node

        # Otherwise, return true at the end of the function
        return True

    def get_number_incoming_control_connections(self, node: BaseNode, connections: Connections) -> int:
        if node.name not in connections.incoming_index:
            return 0

        control_connection_count = 0
        node_connections = connections.incoming_index[node.name]

        for param_name, connection_ids in node_connections.items():
            # Find the parameter to check if it's a control type
            param = node.get_parameter_by_name(param_name)
            if param and ParameterTypeBuiltin.CONTROL_TYPE.value in param.input_types:
                control_connection_count += len(connection_ids)

        return control_connection_count

    def _is_node_in_forward_path(
        self, start_node: BaseNode, target_node: BaseNode, connections: Connections, visited: set[str] | None = None
    ) -> bool:
        """Check if target_node is reachable from start_node through control flow connections."""
        if visited is None:
            visited = set()

        if start_node.name in visited:
            return False
        visited.add(start_node.name)

        # Check ALL outgoing control connections, not just get_next_control_output()
        # This handles IfElse nodes that have multiple possible control outputs
        if start_node.name in connections.outgoing_index:
            for param_name, connection_ids in connections.outgoing_index[start_node.name].items():
                # Find the parameter to check if it's a control type
                param = start_node.get_parameter_by_name(param_name)
                if param and param.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
                    # This is a control parameter - check all its connections
                    for connection_id in connection_ids:
                        if connection_id in connections.connections:
                            connection = connections.connections[connection_id]
                            next_node = connection.target_node

                            if next_node.name == target_node.name:
                                return True

                            # Recursively check the forward path
                            if self._is_node_in_forward_path(next_node, target_node, connections, visited):
                                return True

        return False

    def cleanup_empty_graph_nodes(self, graph_name: str) -> None:
        """Remove nodes from node_to_reference when their graph becomes empty (only in single node resolution)."""
        if graph_name in self.graph_to_nodes:
            for node_name in self.graph_to_nodes[graph_name]:
                self.node_to_reference.pop(node_name, None)
            self.graph_to_nodes.pop(graph_name, None)
