from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.common.directed_graph import DirectedGraph
from griptape_nodes.exe_types.base_iterative_nodes import BaseIterativeStartNode
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import NodeResolutionState

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
                logger.info("DAG: Skipping node '%s' - already visited in this traversal", current_node.name)
                return
            visited.add(current_node.name)

            if current_node.name in self.node_to_reference:
                logger.info("DAG: Skipping node '%s' - already in DAG", current_node.name)
                return

            # Check if we should ignore dependencies (for special nodes like output_selector)
            ignore_data_dependencies = hasattr(current_node, "ignore_dependencies")
            if ignore_data_dependencies:
                logger.info("DAG: Node '%s' ignores dependencies", current_node.name)

            # Process all upstream dependencies first (depth-first traversal)
            for param in current_node.parameters:
                # Skip control flow parameters
                if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                    continue

                # Skip if node ignores dependencies
                if ignore_data_dependencies:
                    continue

                upstream_connection = connections.get_connected_node(current_node, param, include_internal=False)
                if not upstream_connection:
                    continue

                upstream_node, _ = upstream_connection

                # Skip already resolved nodes
                if upstream_node.state == NodeResolutionState.RESOLVED:
                    logger.info(
                        "DAG: Skipping resolved upstream node '%s' for node '%s'",
                        upstream_node.name,
                        current_node.name,
                    )
                    continue

                # Recursively add upstream node
                logger.info(
                    "DAG: Processing upstream dependency '%s' for node '%s'", upstream_node.name, current_node.name
                )
                _add_node_recursive(upstream_node, visited, graph)

                # Add edge from upstream to current
                graph.add_edge(upstream_node.name, current_node.name)

            # Add current node to tracking
            dag_node = DagNode(node_reference=current_node, node_state=NodeState.WAITING)
            self.node_to_reference[current_node.name] = dag_node
            added_nodes.append(current_node)

            # Add to graph
            graph.add_node(node_for_adding=current_node.name)
            self.graph_to_nodes[graph_name].add(current_node.name)

            logger.info("DAG: Added node '%s' to graph '%s' with dependencies", current_node.name, graph_name)

        _add_node_recursive(node, set(), graph)

        return added_nodes

    def add_node(self, node: BaseNode, graph_name: str = "default") -> DagNode:
        """Add just one node to DAG without dependencies (assumes dependencies already exist)."""
        if node.name in self.node_to_reference:
            logger.info("DAG: Node '%s' already exists in graph '%s', returning existing", node.name, graph_name)
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

        logger.info("DAG: Added node '%s' to graph '%s' without dependencies", node.name, graph_name)
        return dag_node

    def clear(self) -> None:
        """Clear all nodes and references from the DAG builder."""
        self.graphs.clear()
        self.node_to_reference.clear()
        self.graph_to_nodes.clear()

    def can_queue_control_node(self, node: DagNode) -> bool:  # noqa: C901, PLR0912
        if len(self.graphs) == 1:
            logger.info("DAG: Node '%s' can queue - only one graph exists", node.node_reference.name)
            return True

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        control_connections = self.get_number_incoming_control_connections(node.node_reference, connections)
        if control_connections == 0:
            logger.info("DAG: Node '%s' can queue - has no incoming control connections", node.node_reference.name)
            return True

        if control_connections == 1:
            # Check if the single incoming control connection node has been resolved
            if node.node_reference.name in connections.incoming_index:
                for param_name, connection_ids in connections.incoming_index[node.node_reference.name].items():
                    param = node.node_reference.get_parameter_by_name(param_name)
                    if param and ParameterTypeBuiltin.CONTROL_TYPE.value in param.input_types:
                        # Found the control connection - check if source node is resolved
                        for connection_id in connection_ids:
                            if connection_id in connections.connections:
                                connection = connections.connections[connection_id]
                                source_node = connection.source_node
                                if source_node.state != NodeResolutionState.RESOLVED:
                                    logger.info(
                                        "DAG: Node '%s' CANNOT queue - incoming control node '%s' not resolved yet",
                                        node.node_reference.name,
                                        source_node.name,
                                    )
                                    return False
            logger.info(
                "DAG: Node '%s' can queue - has 1 incoming control connection and source is resolved",
                node.node_reference.name,
            )
            return True

        logger.info(
            "DAG: Checking if node '%s' can queue (has %d incoming control connections, %d graphs)",
            node.node_reference.name,
            control_connections,
            len(self.graphs),
        )

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
                        logger.info(
                            "DAG: Node '%s' CANNOT queue - still reachable from root node '%s'",
                            node.node_reference.name,
                            root_node.name,
                        )
                        return False  # This graph could still reach the target node

        # Otherwise, return true at the end of the function
        logger.info("DAG: Node '%s' CAN queue - not reachable from any remaining graph roots", node.node_reference.name)
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
                # Skip connections from end node or itself if this is a BaseIterativeStartNode
                if isinstance(node, BaseIterativeStartNode):
                    for connection_id in connection_ids:
                        if connection_id in connections.connections:
                            connection = connections.connections[connection_id]
                            source_node = connection.source_node
                            # Skip if connection is from end node or itself
                            if source_node in (node.end_node, node):
                                continue
                            control_connection_count += 1
                else:
                    control_connection_count += len(connection_ids)

        return control_connection_count

    @staticmethod
    def collect_nodes_in_forward_control_path(
        start_node: BaseNode, end_node: BaseNode, connections: Connections
    ) -> set[str]:
        """Collect all nodes in the forward control path from start_node to end_node.

        Args:
            start_node: The node to start traversal from
            end_node: The node to stop traversal at (inclusive)
            connections: The connections manager

        Returns:
            Set of node names in the control path from start to end (inclusive)
        """
        nodes_in_path: set[str] = set()
        to_visit = [start_node]
        visited = set()

        while to_visit:
            current_node = to_visit.pop(0)

            if current_node.name in visited:
                continue
            visited.add(current_node.name)

            # Add to our collection
            nodes_in_path.add(current_node.name)

            # Stop if we've reached the end node
            if current_node == end_node:
                continue

            # Find all outgoing control connections
            if current_node.name in connections.outgoing_index:
                for param_name, connection_ids in connections.outgoing_index[current_node.name].items():
                    param = current_node.get_parameter_by_name(param_name)
                    if param and param.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
                        for connection_id in connection_ids:
                            if connection_id in connections.connections:
                                connection = connections.connections[connection_id]
                                next_node = connection.target_node
                                if next_node.name not in visited and not connection.is_node_group_internal:
                                    to_visit.append(next_node)

        return nodes_in_path

    @staticmethod
    def collect_data_dependencies_for_node(
        node: BaseNode, connections: Connections, nodes_to_exclude: set[str], visited: set[str]
    ) -> set[str]:
        """Collect data dependencies for a node recursively.

        Args:
            node: The node to collect dependencies for
            connections: The connections manager
            nodes_to_exclude: Set of nodes to exclude (e.g., nodes already in control flow)
            visited: Set of already visited dependency nodes (modified in place)

        Returns:
            Set of dependency node names
        """
        if node.name in visited:
            return set()

        visited.add(node.name)
        dependencies: set[str] = set()

        # Check for ignore_dependencies attribute (like output_selector)
        ignore_data_dependencies = hasattr(node, "ignore_dependencies")
        if ignore_data_dependencies:
            return dependencies

        # Process each parameter looking for data dependencies
        for param in node.parameters:
            # Skip control parameters
            if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                continue

            # Get upstream data connection
            upstream_connection = connections.get_connected_node(node, param, include_internal=False)
            if upstream_connection:
                upstream_node, _ = upstream_connection

                # Skip if already resolved
                if upstream_node.state == NodeResolutionState.RESOLVED:
                    continue

                # Only add if it's not in the exclusion set
                if upstream_node.name not in nodes_to_exclude:
                    dependencies.add(upstream_node.name)
                    # Recursively collect dependencies of this dependency
                    sub_deps = DagBuilder.collect_data_dependencies_for_node(
                        upstream_node, connections, nodes_to_exclude, visited
                    )
                    dependencies.update(sub_deps)

        return dependencies

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
