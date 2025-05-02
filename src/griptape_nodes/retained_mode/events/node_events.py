from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.node_library.library_registry import LibraryNameAndVersion
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
    SetParameterValueRequest,
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
class CreateNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
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
class DeleteNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
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
class GetNodeResolutionStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    metadata: dict
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
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
class GetAllNodeInfoResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: dict
    node_resolution_state: str
    connections: ListConnectionsForNodeResultSuccess
    element_id_to_value: dict[str, ParameterInfoValue]
    root_node_element: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# A Node's state can be serialized to a sequence of commands that the engine runs.
@dataclass
class SerializedNodeCommands:
    """Represents a set of serialized commands for a node, including its creation and modifications.

    This is useful for encapsulating a Node, either for saving a workflow, copy/paste, etc.

    Attributes:
        create_node_command (CreateNodeRequest): The command to create the node.
        element_modification_commands (list[RequestPayload]): A list of commands to create or modify the elements (including Parameters) of the node.
        node_library_details (LibraryNameAndVersion): Details of the library and version used by the node.
    """

    @dataclass
    class IndexedSetParameterValueCommand:
        """Companion class to assign parameter values from our unique values list into node indices, since we can't predict the names.

        Attributes:
            set_parameter_value_command (SetParameterValueRequest): The base set parameter command.
            unique_value_index (int): The index into the unique values list that must be provided when serializing/deserializing,
                used to assign values upon deserialization.
        """

        set_parameter_value_command: SetParameterValueRequest
        unique_value_index: int

    create_node_command: CreateNodeRequest
    element_modification_commands: list[RequestPayload]
    node_library_details: LibraryNameAndVersion


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsRequest(RequestPayload):
    """Request payload to serialize a node into a sequence of commands.

    Attributes:
        node_name (str | None): The name of the node to serialize. If None, the node in the current context is used.
        unique_parameter_values_list (list[Any]): List of unique parameter values. Serialization will check a
            parameter's value against these, appending new values if necessary. NOTE that it modifies the list in-place.
        value_hash_to_unique_value_index (dict[Any, int]): Mapping of hash values to unique parameter value indices.
            If serialization adds new unique values, they are added to this map. NOTE that it modifies the list in-place.
    """

    node_name: str | None = None
    unique_parameter_values_list: list[Any] = field(default_factory=list)
    value_hash_to_unique_value_index: dict[Any, int] = field(default_factory=dict)


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Represents a successful result for serializing a node into a sequence of commands.

    Attributes:
        serialized_node_commands (SerializedNodeCommands): The serialized commands representing the node.
        set_parameter_value_commands (list[SerializedNodeCommands.IndexedSetParameterValueCommand]): A list of
            commands to set parameter values, indexed into the unique values list.
    """

    serialized_node_commands: SerializedNodeCommands
    set_parameter_value_commands: list[SerializedNodeCommands.IndexedSetParameterValueCommand]


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsRequest(RequestPayload):
    serialized_node_commands: SerializedNodeCommands


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    node_name: str


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultFailure(ResultPayloadFailure):
    pass
