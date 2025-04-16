from dataclasses import dataclass
from typing import Any

from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeResultSuccess
from griptape_nodes.retained_mode.events.parameter_events import (
    GetParameterDetailsResultSuccess,
    GetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateNodeRequest(RequestPayload):
    node_type: str
    specific_library_name: str | None = None
    node_name: str | None = None
    override_parent_flow_name: str | None = None
    metadata: dict | None = None
    resolution: str = NodeResolutionState.UNRESOLVED.value
    # initial_setup prevents unnessecary work when we are on loading a workflow from a file.
    initial_setup: bool = False


@dataclass
@PayloadRegistry.register
class CreateNodeResultSuccess(ResultPayloadSuccess):
    node_name: str


@dataclass
@PayloadRegistry.register
class CreateNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class DeleteNodeResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultSuccess(ResultPayloadSuccess):
    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultSuccess(ResultPayloadSuccess):
    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultSuccess(ResultPayloadSuccess):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    node_name: str
    metadata: dict


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultFailure(ResultPayloadFailure):
    pass


# Get all info via a "jumbo" node event. Batches multiple info requests for, say, a GUI.
# ...jumbode?
@dataclass
@PayloadRegistry.register
class GetAllNodeInfoRequest(RequestPayload):
    node_name: str


@dataclass
class ParameterInfoValue:
    details: GetParameterDetailsResultSuccess
    value: GetParameterValueResultSuccess


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultSuccess(ResultPayloadSuccess):
    metadata: dict
    node_resolution_state: str
    connections: ListConnectionsForNodeResultSuccess
    element_id_to_value: dict[str, ParameterInfoValue]
    root_node_element: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultFailure(ResultPayloadFailure):
    pass
