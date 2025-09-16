from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.common.directed_graph import DirectedGraph
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

    def __init__(self) -> None:
        self.graphs = {}
        self.node_to_reference: dict[str, DagNode] = {}

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

        def _add_node_recursive(current_node: BaseNode, visited: set[str], graph: DirectedGraph) -> None:
            if current_node.name in visited:
                return
            visited.add(current_node.name)

            # Skip if already in DAG (use DAG membership, not resolved state)
            if current_node.name in self.node_to_reference:
                logger.info(
                    "Node '%s' already exists in DAG - adding edge to graph '%s' but not creating new DagNode",
                    current_node.name,
                    graph_name,
                )
                return

            # Process dependencies first (depth-first)
            # Skip data dependency processing if node has overridden initialize_spotlight to return None
            # This is necessary for OutputSelector to still work (it doesn't process data dependencies)
            should_process_data_dependencies = current_node.initialize_spotlight() is not None

            for param in current_node.parameters:
                if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                    continue

                # Skip data parameters if node shouldn't process data dependencies (like OutputSelector)
                if not should_process_data_dependencies:
                    continue

                upstream_connection = connections.get_connected_node(current_node, param)
                if upstream_connection:
                    upstream_node, _ = upstream_connection
                    # Don't add nodes that have already been resolved.
                    if upstream_node.state == NodeResolutionState.RESOLVED:
                        continue
                    # If upstream is already in DAG, skip creating edge (it's in another graph)
                    if upstream_node.name in self.node_to_reference:
                        logger.info(
                            "Node '%s' already in DAG - adding cross-graph edge from existing node to '%s' in graph '%s'",
                            upstream_node.name,
                            current_node.name,
                            graph_name,
                        )
                        graph.add_edge(upstream_node.name, current_node.name)
                    # Otherwise, add it to DAG first then create edge
                    else:
                        _add_node_recursive(upstream_node, visited, graph)
                        graph.add_edge(upstream_node.name, current_node.name)

            # Add current node to DAG (but keep original resolution state)

            logger.info("Adding NEW node '%s' to DAG in graph '%s' with state WAITING", current_node.name, graph_name)
            dag_node = DagNode(node_reference=current_node, node_state=NodeState.WAITING)
            self.node_to_reference[current_node.name] = dag_node
            graph.add_node(node_for_adding=current_node.name)
            # DON'T mark as resolved - that happens during actual execution
            added_nodes.append(current_node)

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
        return dag_node

    def clear(self) -> None:
        """Clear all nodes and references from the DAG builder."""
        self.graphs.clear()
        self.node_to_reference.clear()

    def can_queue_control_node(self, node: DagNode, network_name: str) -> bool:
        logger.info(
            "Checking if node '%s' can be queued from network '%s'. Total graphs: %d",
            node.node_reference.name,
            network_name,
            len(self.graphs),
        )
        if len(self.graphs) == 1:
            logger.info("Only one graph exists - node '%s' can be queued", node.node_reference.name)
            return True

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        control_connections = self.get_number_incoming_control_connections(node.node_reference, connections)
        logger.info("Node '%s' has %d incoming control connections", node.node_reference.name, control_connections)
        if control_connections <= 1:
            logger.info("Node '%s' has <= 1 control connections - can be queued", node.node_reference.name)
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
                        logger.info(
                            "Node '%s' is in forward path from root '%s' - cannot queue yet (other graph still active)",
                            node.node_reference.name,
                            root_node.name,
                        )
                        return False  # This graph could still reach the target node

        # Otherwise, return true at the end of the function
        logger.info("No active graphs can reach node '%s' - can be queued", node.node_reference.name)
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
