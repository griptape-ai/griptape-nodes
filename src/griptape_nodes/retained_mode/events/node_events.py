from dataclasses import dataclass
from typing import Any

from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
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
    # If None is passed, assumes we're using the flow in the Current Context
    override_parent_flow_name: str | None = None
    metadata: dict | None = None
    resolution: str = NodeResolutionState.UNRESOLVED.value
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False
    # When True, this Node will be pushed as the current Node within the Current Context.
    set_as_new_context: bool = False


@dataclass
@PayloadRegistry.register
class CreateNodeResultSuccess(ResultPayloadSuccess, WorkflowAlteredMixin):
    node_name: str


@dataclass
@PayloadRegistry.register
class CreateNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context.
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteNodeResultSuccess(ResultPayloadSuccess, WorkflowAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class DeleteNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    metadata: dict
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultSuccess(ResultPayloadSuccess, WorkflowAlteredMixin):
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
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
class ParameterInfoValue:
    details: GetParameterDetailsResultSuccess
    value: GetParameterValueResultSuccess


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultSuccess(ResultPayloadSuccess, WorkflowNotAlteredMixin):
    metadata: dict
    node_resolution_state: str
    connections: ListConnectionsForNodeResultSuccess
    element_id_to_value: dict[str, ParameterInfoValue]
    root_node_element: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultFailure(ResultPayloadFailure, WorkflowNotAlteredMixin):
    pass
