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
    from griptape_nodes.exe_types.node_types import BaseNode, NodeGroup

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
            if current_node.name in visited:
                return
            visited.add(current_node.name)
            # Skip if already in DAG (use DAG membership, not resolved state)
            if current_node.name in self.node_to_reference:
                return
            # Process dependencies first (depth-first)
            ignore_data_dependencies = False
            # This is specifically for output_selector. Overriding 'initialize_spotlight' doesn't work anymore.
            if hasattr(current_node, "ignore_dependencies"):
                ignore_data_dependencies = True
            for param in current_node.parameters:
                if param.type == ParameterTypeBuiltin.CONTROL_TYPE:
                    continue
                if ignore_data_dependencies:
                    continue
                upstream_connection = connections.get_connected_node(current_node, param)
                if upstream_connection:
                    upstream_node, _ = upstream_connection
                    # Don't add nodes that have already been resolved.
                    if upstream_node.state == NodeResolutionState.RESOLVED:
                        continue
                    # If upstream is already in DAG, skip creating edge (it's in another graph)
                    if upstream_node.name in self.node_to_reference:
                        graph.add_edge(upstream_node.name, current_node.name)
                    # Otherwise, add it to DAG first then create edge
                    else:
                        _add_node_recursive(upstream_node, visited, graph)
                        graph.add_edge(upstream_node.name, current_node.name)

            # Add current node to DAG (but keep original resolution state)

            dag_node = DagNode(node_reference=current_node, node_state=NodeState.WAITING)
            self.node_to_reference[current_node.name] = dag_node
            graph.add_node(node_for_adding=current_node.name)

            # Track which nodes belong to this graph
            self.graph_to_nodes[graph_name].add(current_node.name)

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

    def identify_and_process_node_groups(self) -> dict[str, BaseNode]:
        """Identify node groups, validate them, and replace with proxy nodes.

        Scans all nodes in the DAG for non-empty node_group parameter values,
        creates NodeGroup instances, validates they have no intermediate ungrouped nodes,
        and replaces them with NodeGroupProxyNode instances in the DAG.

        Returns:
            Dictionary mapping group IDs to their proxy nodes

        Raises:
            ValueError: If validation fails (e.g., ungrouped nodes between grouped nodes)
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()

        # Step 1: Identify groups by scanning all nodes
        groups = self._identify_node_groups(connections)

        if not groups:
            return {}

        # Step 2: Validate each group
        for group in groups.values():
            group.validate_no_intermediate_nodes(connections.connections)

        # Step 3: Create proxy nodes and replace groups in DAG
        proxy_nodes = {}
        for group_id, group in groups.items():
            proxy_node = self._create_and_install_proxy_node(group_id, group, connections)
            proxy_nodes[group_id] = proxy_node

        return proxy_nodes

    def _identify_node_groups(self, connections: Connections) -> dict[str, NodeGroup]:
        """Identify and build NodeGroup instances from nodes in the DAG.

        Args:
            connections: Connections object for analyzing connection topology

        Returns:
            Dictionary mapping group IDs to NodeGroup instances
        """
        from griptape_nodes.exe_types.node_types import NodeGroup

        groups: dict[str, NodeGroup] = {}

        # Scan all nodes in DAG for group membership
        for dag_node in self.node_to_reference.values():
            node = dag_node.node_reference
            group_id = node.get_parameter_value("job_group")

            # Skip nodes without group assignment or empty group ID
            if not group_id or group_id == "":
                continue

            # Create group if it doesn't exist
            if group_id not in groups:
                groups[group_id] = NodeGroup(group_id=group_id)

            # Add node to group
            groups[group_id].add_node(node)

        # Analyze connections for each group
        for group in groups.values():
            self._analyze_group_connections(group, connections)

        return groups

    def _analyze_group_connections(self, group: NodeGroup, connections: Connections) -> None:
        """Analyze and categorize connections for a node group.

        Categorizes all connections involving group nodes as either:
        - Internal: Both endpoints within the group
        - External incoming: From outside node to group node
        - External outgoing: From group node to outside node

        Args:
            group: NodeGroup to analyze
            connections: Connections object containing all flow connections
        """
        node_names_in_group = set(group.nodes.keys())

        # Analyze all connections in the flow
        for conn in connections.connections.values():
            source_in_group = conn.source_node.name in node_names_in_group
            target_in_group = conn.target_node.name in node_names_in_group

            if source_in_group and target_in_group:
                # Both endpoints in group - internal connection
                group.internal_connections.append(conn)
            elif source_in_group and not target_in_group:
                # From group to outside - external outgoing
                group.external_outgoing_connections.append(conn)
            elif not source_in_group and target_in_group:
                # From outside to group - external incoming
                group.external_incoming_connections.append(conn)

    def _create_and_install_proxy_node(self, group_id: str, group: NodeGroup, connections: Connections) -> BaseNode:
        """Create a proxy node for a group and install it in the DAG.

        Creates a NodeGroupProxyNode, adds it to the DAG, remaps all external
        connections to point to the proxy, and removes the original grouped
        nodes from the DAG.

        Args:
            group_id: Unique identifier for the group
            group: NodeGroup instance to replace
            connections: Connections object for remapping connections

        Returns:
            The created NodeGroupProxyNode
        """
        from griptape_nodes.exe_types.node_types import NodeGroupProxyNode

        # Create proxy node with unique name
        proxy_name = f"__group_proxy_{group_id}"
        proxy_node = NodeGroupProxyNode(name=proxy_name, node_group=group)

        # Determine which graph to add proxy to (use first grouped node's graph)
        target_graph_name = None
        for graph_name, node_set in self.graph_to_nodes.items():
            if any(node_name in node_set for node_name in group.nodes):
                target_graph_name = graph_name
                break

        if target_graph_name is None:
            target_graph_name = "default"

        # Add proxy node to DAG
        self.add_node(proxy_node, target_graph_name)

        # Remap external connections to proxy
        self._remap_connections_to_proxy(group, proxy_node, connections)

        # Remove grouped nodes from DAG
        self._remove_grouped_nodes_from_dag(group)

        return proxy_node

    def _remap_connections_to_proxy(self, group: NodeGroup, proxy_node: BaseNode, connections: Connections) -> None:
        """Remap external connections from group nodes to the proxy node.

        Updates the connection indices and Connection objects to redirect
        external connections through the proxy node instead of the original
        grouped nodes.

        Args:
            group: NodeGroup being replaced
            proxy_node: Proxy node that will handle external connections
            connections: Connections object to update
        """
        # Remap external incoming connections (from outside -> group becomes outside -> proxy)
        for conn in group.external_incoming_connections:
            conn_id = id(conn)

            # Remove old incoming index entry
            if (
                conn.target_node.name in connections.incoming_index
                and conn.target_parameter.name in connections.incoming_index[conn.target_node.name]
            ):
                connections.incoming_index[conn.target_node.name][conn.target_parameter.name].remove(conn_id)

            # Update connection target to proxy
            conn.target_node = proxy_node

            # Add new incoming index entry
            connections.incoming_index.setdefault(proxy_node.name, {}).setdefault(
                conn.target_parameter.name, []
            ).append(conn_id)

        # Remap external outgoing connections (group -> outside becomes proxy -> outside)
        for conn in group.external_outgoing_connections:
            conn_id = id(conn)

            # Remove old outgoing index entry
            if (
                conn.source_node.name in connections.outgoing_index
                and conn.source_parameter.name in connections.outgoing_index[conn.source_node.name]
            ):
                connections.outgoing_index[conn.source_node.name][conn.source_parameter.name].remove(conn_id)

            # Update connection source to proxy
            conn.source_node = proxy_node

            # Add new outgoing index entry
            connections.outgoing_index.setdefault(proxy_node.name, {}).setdefault(
                conn.source_parameter.name, []
            ).append(conn_id)

    def _remove_grouped_nodes_from_dag(self, group: NodeGroup) -> None:
        """Remove all nodes in a group from the DAG graphs and references.

        Args:
            group: NodeGroup whose nodes should be removed from the DAG
        """
        for node_name in group.nodes:
            # Remove from node_to_reference
            if node_name in self.node_to_reference:
                del self.node_to_reference[node_name]

            # Remove from all graphs
            for graph in self.graphs.values():
                if node_name in graph.nodes():
                    graph.remove_node(node_name)

            # Remove from graph_to_nodes tracking
            for node_set in self.graph_to_nodes.values():
                node_set.discard(node_name)
