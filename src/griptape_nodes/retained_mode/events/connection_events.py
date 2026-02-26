from dataclasses import dataclass, field

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
class Waypoint:
    """Position for a connection edge bend point (e.g. in the flow canvas)."""

    x: float
    y: float


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
    # Optional waypoints for the connection (e.g. when loading from file). Ordered list of Waypoint.
    waypoints: list[Waypoint] | None = None


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
    waypoints: list[Waypoint] = field(default_factory=list)


@dataclass
class OutgoingConnection:
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str
    waypoints: list[Waypoint] = field(default_factory=list)


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


# --- Waypoint events ---


@dataclass
@PayloadRegistry.register
class CreateWaypointRequest(RequestPayload):
    """Add a new waypoint to an existing connection.

    Use when: User adds a bend point to an edge in the UI.

    Args:
        source_node_name: Source node of the connection
        source_parameter_name: Source parameter name
        target_node_name: Target node of the connection
        target_parameter_name: Target parameter name
        waypoint: {"x": float, "y": float} position of the new waypoint
        insert_index: Optional 0-based index to insert at. If omitted, append to end.

    Results: CreateWaypointResultSuccess (with updated waypoints) | CreateWaypointResultFailure
    """

    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str
    waypoint: Waypoint
    insert_index: int | None = None


@dataclass
@PayloadRegistry.register
class CreateWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint added successfully. waypoints is the full updated ordered list for the connection."""

    waypoints: list[Waypoint]


@dataclass
@PayloadRegistry.register
class CreateWaypointResultFailure(ResultPayloadFailure):
    """Create waypoint failed. Common causes: connection not found, invalid index or coordinates."""


@dataclass
@PayloadRegistry.register
class RemoveWaypointRequest(RequestPayload):
    """Remove a waypoint from a connection.

    Use when: User removes a bend point from an edge in the UI.

    Args:
        source_node_name: Source node of the connection
        source_parameter_name: Source parameter name
        target_node_name: Target node of the connection
        target_parameter_name: Target parameter name
        waypoint_index: 0-based index of waypoint to remove

    Results: RemoveWaypointResultSuccess (with updated waypoints) | RemoveWaypointResultFailure
    """

    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str
    waypoint_index: int


@dataclass
@PayloadRegistry.register
class RemoveWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint removed successfully. waypoints is the full updated ordered list for the connection."""

    waypoints: list[Waypoint]


@dataclass
@PayloadRegistry.register
class RemoveWaypointResultFailure(ResultPayloadFailure):
    """Remove waypoint failed. Common causes: connection not found, waypoint_index out of range."""


@dataclass
@PayloadRegistry.register
class UpdateWaypointRequest(RequestPayload):
    """Update the position of an existing waypoint.

    Use when: User drags a bend point on an edge in the UI.

    Args:
        source_node_name: Source node of the connection
        source_parameter_name: Source parameter name
        target_node_name: Target node of the connection
        target_parameter_name: Target parameter name
        waypoint_index: 0-based index of waypoint to update
        waypoint: {"x": float, "y": float} new position

    Results: UpdateWaypointResultSuccess (with updated waypoints) | UpdateWaypointResultFailure
    """

    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str
    waypoint_index: int
    waypoint: Waypoint


@dataclass
@PayloadRegistry.register
class UpdateWaypointResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Waypoint updated successfully. waypoints is the full updated ordered list for the connection."""

    waypoints: list[Waypoint]


@dataclass
@PayloadRegistry.register
class UpdateWaypointResultFailure(ResultPayloadFailure):
    """Update waypoint failed. Common causes: connection not found, waypoint_index out of range."""
