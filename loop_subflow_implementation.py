"""
This file contains the implementation for loop subflow management.
It includes methods to handle moving nodes between loop nodes into the appropriate subflow.
"""


def _handle_loop_subflow_management(self, source_node, target_node, parent_flow_name):
    """Handle moving nodes between loop nodes into the appropriate subflow.

    This method checks if the nodes being connected are part of a loop structure
    and moves them to the appropriate subflow if needed. It recursively traverses
    the graph to include all nodes between the start and end loop nodes in the subflow.

    Args:
        source_node: The source node of the connection
        target_node: The target node of the connection
        parent_flow_name: The name of the parent flow
    """
    from griptape_nodes.exe_types.node_types import StartLoopNode, EndLoopNode

    # Check if we're dealing with a loop structure
    if isinstance(source_node, StartLoopNode) and source_node.subflow_name:
        # If connecting from a StartLoopNode to another node, move the target node to the subflow
        if not isinstance(target_node, EndLoopNode):
            # Move the target node and all nodes reachable from it to the subflow
            self._move_node_and_descendants_to_subflow(target_node, source_node.subflow_name)

    elif isinstance(target_node, EndLoopNode) and target_node.subflow_name:
        # If connecting to an EndLoopNode from another node, move the source node to the subflow
        if not isinstance(source_node, StartLoopNode):
            # Move the source node and all nodes that can reach it to the subflow
            self._move_node_and_ancestors_to_subflow(source_node, target_node.subflow_name)


def _move_node_between_flows(self, node, source_flow_name, target_flow_name):
    """Move a node from one flow to another, preserving connections where possible.

    Args:
        node: The node to move
        source_flow_name: The name of the source flow
        target_flow_name: The name of the target flow
    """
    # Get the source and target flows
    source_flow = self.get_flow_by_name(source_flow_name)
    target_flow = self.get_flow_by_name(target_flow_name)

    # Get all connections involving this node before removing it
    incoming_connections = source_flow.connections.get_incoming_connections(node)
    outgoing_connections = source_flow.connections.get_outgoing_connections(node)

    # Remove the node from the source flow and add it to the target flow
    source_flow.remove_node(node.name)
    target_flow.add_node(node)

    # Update the node's parent flow in the NodeManager
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = target_flow_name

    # Recreate connections in the target flow if the connected nodes are also in the target flow
    for conn in incoming_connections:
        source_node = conn.source_node
        source_param = conn.source_parameter
        target_param = conn.target_parameter

        # Check if the source node is also in the target flow
        if GriptapeNodes.NodeManager().get_node_parent_flow_by_name(source_node.name) == target_flow_name:
            # Add the connection to the target flow
            target_flow.add_connection(
                source_node=source_node, source_parameter=source_param, target_node=node, target_parameter=target_param
            )

    for conn in outgoing_connections:
        target_node = conn.target_node
        source_param = conn.source_parameter
        target_param = conn.target_parameter

        # Check if the target node is also in the target flow
        if GriptapeNodes.NodeManager().get_node_parent_flow_by_name(target_node.name) == target_flow_name:
            # Add the connection to the target flow
            target_flow.add_connection(
                source_node=node, source_parameter=source_param, target_node=target_node, target_parameter=target_param
            )


def _move_node_and_descendants_to_subflow(self, node, subflow_name, visited=None):
    """Recursively move a node and all its descendants (via control outputs) to the specified subflow.

    Args:
        node: The node to move
        subflow_name: The name of the subflow to move the node to
        visited: Set of already visited nodes to prevent infinite recursion
    """
    if visited is None:
        visited = set()

    if node.name in visited:
        return

    visited.add(node.name)

    # Get the current parent flow of the node
    node_parent_flow = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(node.name)

    # If the node is not already in the subflow, move it
    if node_parent_flow != subflow_name:
        # Move the node from its current flow to the subflow
        self._move_node_between_flows(node, node_parent_flow, subflow_name)

    # Find all outgoing connections from this node's control outputs
    flow = self.get_flow_by_name(subflow_name)
    for connection in flow.connections.get_outgoing_connections(node):
        source_param = connection.source_parameter
        # Check if this is a control output parameter
        if source_param.name == "control_out":
            # Recursively move the target node and its descendants
            self._move_node_and_descendants_to_subflow(connection.target_node, subflow_name, visited)


def _move_node_and_ancestors_to_subflow(self, node, subflow_name, visited=None):
    """Recursively move a node and all its ancestors (via data inputs) to the specified subflow.

    Args:
        node: The node to move
        subflow_name: The name of the subflow to move the node to
        visited: Set of already visited nodes to prevent infinite recursion
    """
    if visited is None:
        visited = set()

    if node.name in visited:
        return

    visited.add(node.name)

    # Get the current parent flow of the node
    node_parent_flow = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(node.name)

    # If the node is not already in the subflow, move it
    if node_parent_flow != subflow_name:
        # Move the node from its current flow to the subflow
        self._move_node_between_flows(node, node_parent_flow, subflow_name)

    # Find all incoming connections to this node's data inputs
    flow = self.get_flow_by_name(subflow_name)
    for connection in flow.connections.get_incoming_connections(node):
        target_param = connection.target_parameter
        # Check if this is a data input parameter (not control_in)
        if target_param.name != "control_in":
            # Recursively move the source node and its ancestors
            self._move_node_and_ancestors_to_subflow(connection.source_node, subflow_name, visited)
