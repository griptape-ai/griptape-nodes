from pydantic.dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class CreateConnectionRequest(RequestPayload):
    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False


@PayloadRegistry.register
class CreateConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class CreateConnectionResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class DeleteConnectionRequest(RequestPayload):
    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_name: str | None = None
    target_node_name: str | None = None


@PayloadRegistry.register
class DeleteConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class DeleteConnectionResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class ListConnectionsForNodeRequest(RequestPayload):
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


@PayloadRegistry.register
class ListConnectionsForNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@PayloadRegistry.register
class ListConnectionsForNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
