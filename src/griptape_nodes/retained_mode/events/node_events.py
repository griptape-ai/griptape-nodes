from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, NamedTuple, NewType
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


class NewPosition(NamedTuple):
    """The X and Y position for the node to be copied to. Updates in the node metadata."""

    x: float
    y: float


@dataclass
@PayloadRegistry.register
class CreateNodeRequest(RequestPayload):
    """Create a new node in a workflow.

    Use when: Building workflows programmatically, responding to user requests ("add a CSV reader"),
    loading saved workflows. Validates node type exists, generates unique name if needed.

    Args:
        node_type: Class name of the node to create
        specific_library_name: Library to search for the node type (None for any library)
        node_name: Desired name for the node (None for auto-generated)
        override_parent_flow_name: Flow to create the node in (None for current context)
        metadata: Initial metadata for the node (position, display properties)
        resolution: Initial resolution state (defaults to UNRESOLVED)
        initial_setup: Skip setup work when loading from file (defaults to False)
        set_as_new_context: Set this node as current context after creation (defaults to False)

    Results: CreateNodeResultSuccess (with assigned name) | CreateNodeResultFailure (invalid type, missing library, flow not found)
    """

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
    """Node created successfully. Node is now available for parameter setting, connections, and execution.

    Args:
        node_name: Final assigned name (may differ from requested)
        node_type: Class name of created node
        specific_library_name: Library that provided this node type
    """

    node_name: str
    node_type: str
    specific_library_name: str | None = None


@dataclass
@PayloadRegistry.register
class CreateNodeResultFailure(ResultPayloadFailure):
    """Node creation failed.

    Common causes: invalid node_type, missing library, flow not found,
    no current context, or instantiation errors. Workflow unchanged.
    """


@dataclass
@PayloadRegistry.register
class DeleteNodeRequest(RequestPayload):
    """Delete a node from a workflow.

    Use when: Removing obsolete nodes, cleaning up failed nodes, restructuring workflows,
    implementing undo. Handles cascading cleanup of connections and execution cancellation.

    Args:
        node_name: Name of the node to delete (None for current context node)

    Results: DeleteNodeResultSuccess | DeleteNodeResultFailure (node not found, cleanup failed)
    """

    # If None is passed, assumes we're using the Node in the Current Context.
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Node deleted successfully. Node and all connections removed, no longer available for use."""


@dataclass
@PayloadRegistry.register
class DeleteNodeResultFailure(ResultPayloadFailure):
    """Node deletion failed.

    Common causes: node not found, no current context,
    execution cancellation failed, or connection cleanup failed. Workflow unchanged.
    """


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateRequest(RequestPayload):
    """Get the current resolution state of a node.

    Use when: Checking if node is ready to execute, monitoring execution progress,
    workflow orchestration, debugging. States: UNRESOLVED -> RESOLVED -> EXECUTING -> COMPLETED/FAILED

    Args:
        node_name: Name of the node to check (None for current context node)

    Results: GetNodeResolutionStateResultSuccess (with state) | GetNodeResolutionStateResultFailure (node not found)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node resolution state retrieved successfully.

    Args:
        state: Current state (UNRESOLVED, RESOLVED, EXECUTING, COMPLETED, FAILED)
    """

    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Resolution state retrieval failed. Common causes: node not found, no current context."""


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    """List all parameter names available on a node.

    Use when: Parameter discovery, validation before setting values, generating UIs,
    implementing completion features. Names can be used with GetParameterValue, SetParameterValue, connections.

    Args:
        node_name: Name of the node to list parameters for (None for current context node)

    Results: ListParametersOnNodeResultSuccess (with parameter names) | ListParametersOnNodeResultFailure (node not found)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Parameter names retrieved successfully.

    Args:
        parameter_names: List of parameter names available on the node
    """

    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Parameter listing failed. Common causes: node not found, no current context."""


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    """Retrieve metadata associated with a node.

    Use when: Getting node position for layout, retrieving custom properties, implementing selection,
    saving/loading workflow layout. Metadata doesn't affect execution but provides workflow context.

    Args:
        node_name: Name of the node to get metadata for (None for current context node)

    Results: GetNodeMetadataResultSuccess (with metadata dict) | GetNodeMetadataResultFailure (node not found)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node metadata retrieved successfully.

    Args:
        metadata: Dictionary containing position, display properties, custom user data
    """

    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Metadata retrieval failed. Common causes: node not found, no current context."""


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    """Update metadata associated with a node.

    Use when: Updating node position, storing custom properties/annotations, implementing styling,
    saving user preferences. Metadata doesn't affect execution but provides workflow context.

    Args:
        metadata: Dictionary of metadata to set (position, display properties, custom data)
        node_name: Name of the node to update metadata for (None for current context node)

    Results: SetNodeMetadataResultSuccess | SetNodeMetadataResultFailure (node not found, update error)
    """

    metadata: dict
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Node metadata updated successfully. New metadata stored and available for future requests."""


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultFailure(ResultPayloadFailure):
    """Metadata update failed. Common causes: node not found, no current context, invalid metadata format."""


# Get all info via a "jumbo" node event. Batches multiple info requests for, say, a GUI.
# ...jumbode?
@dataclass
@PayloadRegistry.register
class GetAllNodeInfoRequest(RequestPayload):
    """Retrieve comprehensive information about a node in a single call.

    Use when: Populating UIs, implementing node inspection/debugging, gathering complete state
    for serialization, optimizing performance. Batches metadata, resolution state, connections, parameters.

    Args:
        node_name: Name of the node to get information for (None for current context node)

    Results: GetAllNodeInfoResultSuccess (with comprehensive info) | GetAllNodeInfoResultFailure (node not found)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
class ParameterInfoValue:
    details: GetParameterDetailsResultSuccess
    value: GetParameterValueResultSuccess


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Comprehensive node information retrieved successfully.

    Args:
        metadata: Node metadata (position, display properties, etc.)
        node_resolution_state: Current execution state
        connections: All incoming and outgoing connections
        element_id_to_value: Parameter details and values by element ID
        root_node_element: Root element information
    """

    metadata: dict
    node_resolution_state: str
    locked: bool
    connections: ListConnectionsForNodeResultSuccess
    element_id_to_value: dict[str, ParameterInfoValue]
    root_node_element: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Comprehensive node information retrieval failed.

    Common causes: node not found, no current context, partial failure in gathering information components.
    """


@dataclass
@PayloadRegistry.register
class SetLockNodeStateRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Lock a node.

    Use when: Implementing locking functionality, preventing changes to nodes.

    Args:
        node_name: Name of the node to lock
        lock: Whether to lock or unlock the node. If true, the node will be locked, otherwise it will be unlocked.

    Results: SetLockNodeStateResultSuccess (node locked) | SetLockNodeStateResultFailure (node not found)
    """

    node_name: str | None
    lock: bool


@dataclass
@PayloadRegistry.register
class SetLockNodeStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Node locked successfully."""

    node_name: str
    locked: bool


@dataclass
@PayloadRegistry.register
class SetLockNodeStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node failed to lock."""


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
    lock_node_command: SetLockNodeStateRequest | None = None
    node_uuid: NodeUUID = field(default_factory=lambda: SerializedNodeCommands.NodeUUID(str(uuid4())))


@dataclass
class SerializedParameterValueTracker:
    """Tracks the serialization state of parameter value hashes.

    This class manages the relationship between value hashes and their unique UUIDs,
    indicating whether a value is serializable or not. It allows the addition of both
    serializable and non-serializable value hashes and provides methods to retrieve
    the serialization state and unique UUIDs for given value hashes.

    Attributes:
        _value_hash_to_unique_value_uuid (dict[Any, SerializedNodeCommands.UniqueParameterValueUUID]):
            A dictionary mapping value hashes to their unique UUIDs when they are serializable.
        _non_serializable_value_hashes (set[Any]):
            A set of value hashes that are not serializable.
    """

    class TrackerState(Enum):
        """State of a value hash in the tracker."""

        NOT_IN_TRACKER = auto()
        SERIALIZABLE = auto()
        NOT_SERIALIZABLE = auto()

    _value_hash_to_unique_value_uuid: dict[Any, SerializedNodeCommands.UniqueParameterValueUUID] = field(
        default_factory=dict
    )
    _non_serializable_value_hashes: set[Any] = field(default_factory=set)

    def get_tracker_state(self, value_hash: Any) -> TrackerState:
        if value_hash in self._non_serializable_value_hashes:
            return SerializedParameterValueTracker.TrackerState.NOT_SERIALIZABLE
        if value_hash in self._value_hash_to_unique_value_uuid:
            return SerializedParameterValueTracker.TrackerState.SERIALIZABLE
        return SerializedParameterValueTracker.TrackerState.NOT_IN_TRACKER

    def add_as_serializable(
        self, value_hash: Any, unique_value_uuid: SerializedNodeCommands.UniqueParameterValueUUID
    ) -> None:
        self._value_hash_to_unique_value_uuid[value_hash] = unique_value_uuid

    def add_as_not_serializable(self, value_hash: Any) -> None:
        self._non_serializable_value_hashes.add(value_hash)

    def get_uuid_for_value_hash(self, value_hash: Any) -> SerializedNodeCommands.UniqueParameterValueUUID:
        return self._value_hash_to_unique_value_uuid[value_hash]

    def get_serializable_count(self) -> int:
        return len(self._value_hash_to_unique_value_uuid)


@dataclass
@PayloadRegistry.register
class SerializeNodeToCommandsRequest(RequestPayload):
    """Serialize a node into a sequence of commands.

    Use when: Implementing copy/paste, exporting nodes, creating templates, backing up nodes.
    Captures complete node state including parameters and connections.

    Args:
        node_name: Name of the node to serialize (None for current context node)
        unique_parameter_uuid_to_values: Mapping of UUIDs to unique parameter values (modified in-place)
        serialized_parameter_value_tracker: Tracks serialization state of parameter values

    Results: SerializeNodeToCommandsResultSuccess (with commands) | SerializeNodeToCommandsResultFailure (serialization error)
    """

    node_name: str | None = None
    unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any] = field(
        default_factory=dict
    )
    serialized_parameter_value_tracker: SerializedParameterValueTracker = field(
        default_factory=SerializedParameterValueTracker
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
class SerializedSelectedNodesCommands:
    @dataclass
    class IndirectConnectionSerialization:
        """Companion class to create connections from node IDs in a serialization, since we can't predict the names.

        These are UUIDs referencing into the serialized_node_commands we maintain.

        Attributes:
            source_node_uuid (SerializedNodeCommands.NodeUUID): UUID of the source node, as stored within the serialization.
            source_parameter_name (str): Name of the source parameter.
            target_node_uuid (SerializedNodeCommands.NodeUUID): UUID of the target node.
            target_parameter_name (str): Name of the target parameter.
        """

        source_node_uuid: SerializedNodeCommands.NodeUUID
        source_parameter_name: str
        target_node_uuid: SerializedNodeCommands.NodeUUID
        target_parameter_name: str

    serialized_node_commands: list[SerializedNodeCommands]
    set_parameter_value_commands: dict[
        SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]
    ]
    set_lock_commands_per_node: dict[SerializedNodeCommands.NodeUUID, SetLockNodeStateRequest]
    serialized_connection_commands: list[IndirectConnectionSerialization]


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Serialize multiple selected nodes into commands.

    Use when: Implementing copy/paste, exporting workflow sections, creating templates,
    backing up workflows, transferring configurations. Preserves nodes and interconnections.

    Args:
        nodes_to_serialize: List of node identifiers (each containing [node_name, timestamp])

    Results: SerializeSelectedNodesToCommandsResultSuccess (with commands) | SerializeSelectedNodesToCommandsResultFailure (node not found, serialization error)
    """

    # They will be passed with node_name, timestamp
    nodes_to_serialize: list[list[str]]


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Selected nodes serialized successfully.

    Preserves complete structure including node configurations, parameter values, and connection relationships.

    Args:
        serialized_selected_node_commands: Complete serialized representation
    """

    # They will be passed with node_name, timestamp
    # Could be a flow command if it's all nodes in a flow.
    serialized_selected_node_commands: SerializedSelectedNodesCommands


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Selected nodes serialization failed.

    Common causes: nodes not found, non-serializable parameter values, connection resolution failures.
    """


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Recreate nodes from serialized commands.

    Use when: Implementing paste functionality, importing configurations, restoring from backups,
    duplicating complex structures. Creates new nodes with unique names and restores parameters/connections.

    Args:
        positions: List of positions for the recreated nodes (None for default positions)

    Results: DeserializeSelectedNodesFromCommandsResultSuccess (with node names) | DeserializeSelectedNodesFromCommandsResultFailure (deserialization error)
    """

    positions: list[NewPosition] | None = None


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Nodes recreated successfully from serialized commands. Parameter values and connections restored.

    Args:
        node_names: List of names assigned to newly created nodes
    """

    node_names: list[str]


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Nodes recreation failed.

    Common causes: invalid/corrupted commands, missing node types/libraries,
    parameter deserialization failures, connection creation errors.
    """


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsRequest(RequestPayload):
    """Recreate a single node from serialized commands.

    Use when: Restoring individual nodes from backups/templates, implementing node-level copy/paste,
    loading configurations, creating from templates. Creates new node with unique name and restores parameters.

    Args:
        serialized_node_commands: Serialized node commands containing complete node state

    Results: DeserializeNodeFromCommandsResultSuccess (with node name) | DeserializeNodeFromCommandsResultFailure (deserialization error)
    """

    serialized_node_commands: SerializedNodeCommands


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Node recreated successfully from serialized commands. Parameter values restored.

    Args:
        node_name: Name assigned to newly created node
    """

    node_name: str


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultFailure(ResultPayloadFailure):
    """Node recreation failed.

    Common causes: invalid/corrupted commands, missing node type/library,
    parameter deserialization failures, creation errors or constraints.
    """


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Duplicate selected nodes with new positions.

    Use when: Implementing duplicate functionality, creating multiple instances of same configuration,
    expanding workflows by replicating patterns, quick copying without serialization overhead.
    Preserves connections between duplicated nodes.

    Args:
        nodes_to_duplicate: List of node identifiers to duplicate (each containing [node_name, timestamp])
        positions: List of positions for the duplicated nodes (None for default positions)

    Results: DuplicateSelectedNodesResultSuccess (with node names) | DuplicateSelectedNodesResultFailure (duplication error)
    """

    nodes_to_duplicate: list[list[str]]
    positions: list[NewPosition] | None = None


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Nodes duplicated successfully. Configuration and connections preserved.

    Args:
        node_names: List of names assigned to newly duplicated nodes
    """

    node_names: list[str]


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Node duplication failed.

    Common causes: nodes not found, constraints/conflicts,
    insufficient resources, connection duplication failures.
    """
