from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
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
class CreateConnectionResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class CreateConnectionResult_Failure(ResultPayload_Failure):
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
class DeleteConnectionResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionResult_Failure(ResultPayload_Failure):
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
class ListConnectionsForNodeResult_Success(ResultPayload_Success):
    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResult_Failure(ResultPayload_Failure):
    pass
