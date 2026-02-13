from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateConnectionRequest(RequestPayload):
    """Create a connection between two node parameters.

    Use when: Connecting node outputs to inputs, building data flow between nodes,
    loading saved workflows. Validates type compatibility and connection rules.

    Args:
        source_parameter_name: Name of the parameter providing the data
        target_parameter_name: Name of the parameter receiving the data
        source_node_name: Name of the source node (None for current context)
        target_node_name: Name of the target node (None for current context)
        initial_setup: Skip setup work when loading from file
        is_node_group_internal: Mark this connection as internal to a node group (for DAG building)

    Results: CreateConnectionResultSuccess | CreateConnectionResultFailure (incompatible types, invalid nodes/parameters)
    """

    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False
    # Mark this connection as internal to a node group proxy parameter
    is_node_group_internal: bool = False
    # Waypoints for the connection (ordered list of {x, y} coordinates)
    waypoints: list[dict[str, float]] | None = None


@dataclass
@PayloadRegistry.register
class CreateConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Connection created successfully between parameters."""


@dataclass
@PayloadRegistry.register
class CreateConnectionResultFailure(ResultPayloadFailure):
    """Connection creation failed.

    Common causes: incompatible types, nodes/parameters not found,
    connection already exists, circular dependency.
    """


@dataclass
@PayloadRegistry.register
class DeleteConnectionRequest(RequestPayload):
    """Delete a connection between two node parameters.

    Use when: Removing unwanted connections, restructuring workflows, disconnecting nodes,
    updating data flow. Cleans up connection state and updates node resolution.

    Args:
        source_parameter_name: Name of the parameter providing the data
        target_parameter_name: Name of the parameter receiving the data
        source_node_name: Name of the source node (None for current context)
        target_node_name: Name of the target node (None for current context)

    Results: DeleteConnectionResultSuccess | DeleteConnectionResultFailure (connection not found, nodes/parameters not found)
    """

    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Connection deleted successfully. Connection state cleaned up."""


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultFailure(ResultPayloadFailure):
    """Connection deletion failed. Common causes: connection not found, nodes/parameters not found."""


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeRequest(RequestPayload):
    """List all connections for a specific node.

    Use when: Inspecting node connectivity, building connection visualizations,
    debugging data flow, validating workflow structure.

    Args:
        node_name: Name of the node to list connections for (None for current context)
        include_internal: Whether to include internal connections (connections where both nodes are in the same group). Defaults to True.

    Results: ListConnectionsForNodeResultSuccess (with connection lists) | ListConnectionsForNodeResultFailure (node not found)
    """

    # If node name is None, use the Current Context
    node_name: str | None = None
    # Whether to include internal connections to groups (defaults to True for backward compatibility)
    include_internal: bool = True


@dataclass
class IncomingConnection:
    source_node_name: str
    source_parameter_name: str
    target_parameter_name: str
    waypoints: list[dict[str, float]] | None = None


@dataclass
class OutgoingConnection:
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str
    waypoints: list[dict[str, float]] | None = None


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node connections retrieved successfully.

    Args:
        incoming_connections: List of connections feeding into this node
        outgoing_connections: List of connections from this node to others
    """

    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node connections listing failed. Common causes: node not found, no current context."""


@dataclass
@PayloadRegistry.register
class CreateWaypointRequest(RequestPayload):
    """Add a new waypoint to an existing connection.

    Use when: User adds a waypoint to a connection in the frontend to control the visual path.

    Args:
        source_node_name: Name of the source node (None for current context)
        source_parameter_name: Name of the source parameter
        target_node_name: Name of the target node (None for current context)
        target_parameter_name: Name of the target parameter
        waypoint: Dictionary with 'x' and 'y' coordinates for the waypoint
        insert_index: Optional position to insert waypoint (0-based). If omitted, append to end

    Results: CreateWaypointResultSuccess | CreateWaypointResultFailure (connection not found, invalid index)
    """

    source_parameter_name: str
    target_parameter_name: str
    waypoint: dict[str, float]
    source_node_name: str | None = None
    target_node_name: str | None = None
    insert_index: int | None = None


@dataclass
@PayloadRegistry.register
class CreateWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint created successfully.

    Args:
        connection: Updated connection information with waypoints
    """

    connection: IncomingConnection | OutgoingConnection


@dataclass
@PayloadRegistry.register
class CreateWaypointResultFailure(ResultPayloadFailure):
    """Waypoint creation failed. Common causes: connection not found, invalid index, invalid coordinates."""


@dataclass
@PayloadRegistry.register
class RemoveWaypointRequest(RequestPayload):
    """Remove a waypoint from a connection.

    Use when: User removes a waypoint from a connection in the frontend.

    Args:
        source_node_name: Name of the source node (None for current context)
        source_parameter_name: Name of the source parameter
        target_node_name: Name of the target node (None for current context)
        target_parameter_name: Name of the target parameter
        waypoint_index: 0-based index of waypoint to remove

    Results: RemoveWaypointResultSuccess | RemoveWaypointResultFailure (connection not found, invalid index)
    """

    source_parameter_name: str
    target_parameter_name: str
    waypoint_index: int
    source_node_name: str | None = None
    target_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class RemoveWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint removed successfully.

    Args:
        connection: Updated connection information with waypoints
    """

    connection: IncomingConnection | OutgoingConnection


@dataclass
@PayloadRegistry.register
class RemoveWaypointResultFailure(ResultPayloadFailure):
    """Waypoint removal failed. Common causes: connection not found, invalid index."""


@dataclass
@PayloadRegistry.register
class UpdateWaypointRequest(RequestPayload):
    """Update the position of an existing waypoint.

    Use when: User drags a waypoint to a new position in the frontend.

    Args:
        source_node_name: Name of the source node (None for current context)
        source_parameter_name: Name of the source parameter
        target_node_name: Name of the target node (None for current context)
        target_parameter_name: Name of the target parameter
        waypoint_index: 0-based index of waypoint to update
        waypoint: Dictionary with 'x' and 'y' coordinates for the updated waypoint

    Results: UpdateWaypointResultSuccess | UpdateWaypointResultFailure (connection not found, invalid index)
    """

    source_parameter_name: str
    target_parameter_name: str
    waypoint_index: int
    waypoint: dict[str, float]
    source_node_name: str | None = None
    target_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class UpdateWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint updated successfully.

    Args:
        connection: Updated connection information with waypoints
    """

    connection: IncomingConnection | OutgoingConnection


@dataclass
@PayloadRegistry.register
class UpdateWaypointResultFailure(ResultPayloadFailure):
    """Waypoint update failed. Common causes: connection not found, invalid index, invalid coordinates."""
