from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateConnectionRequest(RequestPayload):
    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str


@dataclass
@PayloadRegistry.register
class CreateConnectionResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class CreateConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionRequest(RequestPayload):
    source_node_name: str
    source_parameter_name: str
    target_node_name: str
    target_parameter_name: str


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeRequest(RequestPayload):
    node_name: str


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
class ListConnectionsForNodeResultSuccess(ResultPayloadSuccess):
    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultFailure(ResultPayloadFailure):
    pass
