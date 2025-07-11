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
    """Creates a connection between two parameters.

    Args:
        source_parameter_name (str): Name of the source parameter.
        target_parameter_name (str): Name of the target parameter.
        source_node_name (str | None): Name of the source node. If None, uses the Current Context.
        target_node_name (str | None): Name of the target node. If None, uses the Current Context.
        initial_setup (bool): If True, prevents unnecessary work when loading a workflow from a file.

    Returns:
        ResultPayload: Contains the result of the creation.

    Example:
        # Create a connection between two parameters
        CreateConnectionRequest(
            source_parameter_name="source_param",
            target_parameter_name="target_param",
            source_node_name="source_node",
            target_node_name="target_node"
        )
    """

    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False


@dataclass
@PayloadRegistry.register
class CreateConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class CreateConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionRequest(RequestPayload):
    """Deletes a connection between two parameters.

    Args:
        source_parameter_name (str): Name of the source parameter.
        target_parameter_name (str): Name of the target parameter.
        source_node_name (str | None): Name of the source node. If None, uses the Current Context.
        target_node_name (str | None): Name of the target node. If None, uses the Current Context.

    Returns:
        ResultPayload: Contains the result of the deletion.

    Example:
        # Delete a connection between two parameters
        DeleteConnectionRequest(
            source_parameter_name="source_param",
            target_parameter_name="target_param",
            source_node_name="source_node",
            target_node_name="target_node"
        )
    """

    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeRequest(RequestPayload):
    """Gets the current connections for a node.

    This includes both incoming and outgoing connections.

    Args:
        node_name (str): Name of the node to check.

    Returns:
        ResultPayload: Contains the connections for the node.

    Example:
        # List connections for a node
        ListConnectionsForNodeRequest("my_node")
    """

    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
class IncomingConnection:
    source_node_name: str
    source_parameter_name: str
    target_parameter_name: str


@dataclass
class OutgoingConnection:
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
