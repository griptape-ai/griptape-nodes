from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.connection_events import ListConnectionsForNodeResult_Success
from griptape_nodes.retained_mode.events.parameter_events import (
    GetParameterDetailsResult_Success,
    GetParameterValueResult_Success,
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


@dataclass
@PayloadRegistry.register
class CreateNodeResult_Success(ResultPayload_Success):
    node_name: str


@dataclass
@PayloadRegistry.register
class CreateNodeResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class DeleteNodeResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResult_Success(ResultPayload_Success):
    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResult_Success(ResultPayload_Success):
    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    node_name: str


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResult_Success(ResultPayload_Success):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    node_name: str
    metadata: dict


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResult_Failure(ResultPayload_Failure):
    pass


# Get all info via a "jumbo" node event. Batches multiple info requests for, say, a GUI.
# ...jumbode?
@dataclass
@PayloadRegistry.register
class GetAllNodeInfoRequest(RequestPayload):
    node_name: str


@dataclass
class ParameterInfoValue:
    details: GetParameterDetailsResult_Success
    value: GetParameterValueResult_Success


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResult_Success(ResultPayload_Success):
    metadata: dict
    node_resolution_state: str
    connections: ListConnectionsForNodeResult_Success
    parameter_name_to_info: dict[str, ParameterInfoValue]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResult_Failure(ResultPayload_Failure):
    pass
