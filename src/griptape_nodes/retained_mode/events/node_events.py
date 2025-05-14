from dataclasses import dataclass, field
from typing import Any, NewType
from uuid import uuid4

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
        node_uuid (NodeUUID): The UUID of this particular node. During deserialization, this UUID will be used to correlate this node's instance
            with the connections and parameter values necessary. We cannot use node name because Griptape Nodes enforces unique names, and we cannot
            predict the name that will be selected upon instantiation. Similarly, the same serialized node may be deserialized multiple times, such
            as during copy/paste or duplicate.
    """

    # Have to use str instead of the UUID class because it's not JSON serializable >:-/
    NodeUUID = NewType("NodeUUID", str)
    UniqueParameterValueUUID = NewType("UniqueParameterValueUUID", str)

    @dataclass
    class IndirectSetParameterValueCommand:
        """Companion class to assign parameter values from our unique values collection, since we can't predict the names.

        Attributes:
            set_parameter_value_command (SetParameterValueRequest): The base set parameter command.
            unique_value_uuid (SerializedNodeCommands.UniqueParameterValue.UniqueParameterValueUUID): The UUID into the
                unique values dictionary that must be provided when serializing/deserializing, used to assign values upon deserialization.
        """

        set_parameter_value_command: SetParameterValueRequest
        unique_value_uuid: "SerializedNodeCommands.UniqueParameterValueUUID"

    create_node_command: CreateNodeRequest
    element_modification_commands: list[RequestPayload]
    node_library_details: LibraryNameAndVersion
    node_uuid: NodeUUID = field(default_factory=lambda: SerializedNodeCommands.NodeUUID(str(uuid4())))


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsRequest(RequestPayload):
    """Request payload to serialize a node into a sequence of commands.

    Attributes:
        node_name (str | None): The name of the node to serialize. If None, the node in the current context is used.
        unique_parameter_uuid_to_values (dict[SerializedNodeCommands.UniqueParameterValueUUID, Any]): Mapping of
            UUIDs to unique parameter values. Serialization will check a parameter's value against these, inserting
            new values if necessary. NOTE that it modifies the dict in-place.
        value_hash_to_unique_value_uuid (dict[Any, SerializedNodeCommands.UniqueParameterValueUUID]): Mapping of hash
            values to unique parameter value UUIDs. If serialization adds new unique values, they are added to this map.
            NOTE that it modifies the dict in-place.
    """

    node_name: str | None = None
    unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any] = field(
        default_factory=dict
    )
    value_hash_to_unique_value_uuid: dict[Any, SerializedNodeCommands.UniqueParameterValueUUID] = field(
        default_factory=dict
    )


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Represents a successful result for serializing a node into a sequence of commands.

    Attributes:
        serialized_node_commands (SerializedNodeCommands): The serialized commands representing the node.
        set_parameter_value_commands (list[SerializedNodeCommands.IndirectSetParameterValueCommand]): A list of
            commands to set parameter values, keyed into the unique values dictionary.
    """

    serialized_node_commands: SerializedNodeCommands
    set_parameter_value_commands: list[SerializedNodeCommands.IndirectSetParameterValueCommand]


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
