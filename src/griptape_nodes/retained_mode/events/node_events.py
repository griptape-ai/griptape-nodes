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
    """Request to create a new node in a workflow.

    This request instructs the system to instantiate a new node of the specified type within
    a flow. Agents use this to dynamically add processing components to workflows, such as
    adding a text processing node, an image generator, or a data transformation step.

    When would an agent use this?
    - Building a workflow programmatically by adding nodes step by step
    - Creating nodes in response to user requests ("add a CSV reader node")
    - Dynamically expanding workflows based on data or conditions
    - Loading saved workflows that contain node definitions

    The request validates the node type exists, ensures the parent flow exists, generates
    a unique name if none provided, and handles initial setup and context management.

    Result types:
    - CreateNodeResultSuccess: Node created successfully with assigned name
    - CreateNodeResultFailure: Failed due to invalid node type, missing library,
      flow not found, or other creation errors

    Args:
        node_type: The class name of the node to create (e.g., "TextInputNode")
        specific_library_name: Optional library name if node type exists in multiple libraries
        node_name: Desired name for the node (auto-generated if None)
        override_parent_flow_name: Flow to add node to (uses current context if None)
        metadata: Initial metadata dict for the node (position, properties, etc.)
        resolution: Initial resolution state (defaults to UNRESOLVED)
        initial_setup: Skip unnecessary work when loading from file
        set_as_new_context: Make this node the current context node
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
    """Successful result when a node is created.

    This result confirms that a node was successfully instantiated and added to the workflow.
    The node is now available for parameter setting, connection creation, and execution.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    Args:
        node_name: The final assigned name of the created node (may differ from requested name)
        node_type: The class name of the created node
        specific_library_name: The library that provided this node type
    """

    node_name: str
    node_type: str
    specific_library_name: str | None = None


@dataclass
@PayloadRegistry.register
class CreateNodeResultFailure(ResultPayloadFailure):
    """Failed result when node creation fails.

    This result indicates that the node could not be created. Common failure reasons include:
    - Invalid node_type that doesn't exist in any loaded library
    - Specified library not found or not loaded
    - Parent flow not found (if override_parent_flow_name provided)
    - No current context flow (if override_parent_flow_name is None)
    - Node instantiation failed due to missing dependencies or initialization errors

    When this occurs, the workflow remains unchanged and no new node is added.
    """


@dataclass
@PayloadRegistry.register
class DeleteNodeRequest(RequestPayload):
    """Request to delete a node from a workflow.

    This request removes a node from its parent flow and cleans up all associated connections.
    Agents use this to dynamically remove nodes from workflows, such as removing obsolete
    processing steps or cleaning up failed node instances.

    When would an agent use this?
    - Removing nodes that are no longer needed in a workflow
    - Cleaning up failed or problematic nodes
    - Dynamically restructuring workflows by removing components
    - Implementing undo functionality for node creation

    The request handles cascading cleanup by removing all incoming and outgoing connections
    from the node before deletion. If the node is currently executing, the operation will
    be cancelled first.

    Result types:
    - DeleteNodeResultSuccess: Node and all connections removed successfully
    - DeleteNodeResultFailure: Failed due to node not found, execution cancellation
      failed, or connection cleanup errors

    Args:
        node_name: Name of the node to delete (uses current context node if None)
    """

    # If None is passed, assumes we're using the Node in the Current Context.
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successful result when a node is deleted.

    This result confirms that the node was successfully removed from the workflow along
    with all its connections. The node is no longer available for use and cannot be
    referenced in future operations.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    No return data is provided as the node no longer exists.
    """


@dataclass
@PayloadRegistry.register
class DeleteNodeResultFailure(ResultPayloadFailure):
    """Failed result when node deletion fails.

    This result indicates that the node could not be deleted. Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)
    - Parent flow not found (internal consistency error)
    - Execution cancellation failed (node was running and couldn't be stopped)
    - Connection cleanup failed (unable to remove associated connections)

    When this occurs, the workflow remains unchanged and the node is still present.
    """


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateRequest(RequestPayload):
    """Request to get the current resolution state of a node.

    This request retrieves the execution state of a node, which indicates whether it's
    ready to run, currently running, completed, or failed. Agents use this to understand
    workflow execution status and make decisions about next steps.

    When would an agent use this?
    - Checking if a node is ready to execute (has all required inputs)
    - Monitoring execution progress in a workflow
    - Determining which nodes need attention or parameter values
    - Implementing workflow orchestration logic
    - Debugging execution flow issues

    The resolution state follows the lifecycle: UNRESOLVED -> RESOLVED -> EXECUTING -> COMPLETED/FAILED

    Result types:
    - GetNodeResolutionStateResultSuccess: Returns the current state string
    - GetNodeResolutionStateResultFailure: Failed due to node not found

    Args:
        node_name: Name of the node to check (uses current context node if None)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result containing the node's resolution state.

    This result provides the current execution state of the node. The state indicates
    where the node is in its lifecycle and what actions are possible.

    Common states include:
    - UNRESOLVED: Node lacks required inputs or has validation issues
    - RESOLVED: Node has all inputs and is ready to execute
    - EXECUTING: Node is currently running
    - COMPLETED: Node finished successfully
    - FAILED: Node execution failed

    The workflow is not altered by this read-only operation.

    Args:
        state: String representation of the NodeResolutionState enum value
    """

    state: str


@dataclass
@PayloadRegistry.register
class GetNodeResolutionStateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when resolution state cannot be retrieved.

    This result indicates that the node's resolution state could not be determined.
    Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)

    When this occurs, the workflow remains unchanged and no state information is available.
    """


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeRequest(RequestPayload):
    """Request to list all parameter names available on a node.

    This request retrieves the names of all parameters that exist on a specific node.
    Agents use this for parameter discovery, validation, and UI generation. This is
    essential for understanding what inputs and outputs a node provides.

    When would an agent use this?
    - Discovering what parameters are available on a node for connection or value setting
    - Validating that a required parameter exists before attempting to set its value
    - Generating user interfaces that show available node parameters
    - Implementing parameter completion or suggestion features
    - Debugging parameter-related issues

    The returned parameter names can be used with other parameter-related requests
    like GetParameterValue, SetParameterValue, or connection operations.

    Result types:
    - ListParametersOnNodeResultSuccess: Returns list of parameter names
    - ListParametersOnNodeResultFailure: Failed due to node not found

    Args:
        node_name: Name of the node to list parameters for (uses current context node if None)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result containing the node's parameter names.

    This result provides a list of all parameter names available on the node.
    These names can be used to get/set parameter values, create connections,
    or discover the node's interface.

    The workflow is not altered by this read-only operation.

    Args:
        parameter_names: List of parameter names available on the node
    """

    parameter_names: list[str]


@dataclass
@PayloadRegistry.register
class ListParametersOnNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when parameter listing fails.

    This result indicates that the node's parameters could not be retrieved.
    Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)

    When this occurs, the workflow remains unchanged and no parameter information is available.
    """


@dataclass
@PayloadRegistry.register
class GetNodeMetadataRequest(RequestPayload):
    """Request to retrieve metadata associated with a node.

    This request gets the metadata dictionary for a node, which contains information
    like position coordinates, display properties, custom user data, and other
    non-functional attributes. Agents use this to understand node presentation and
    user-defined properties.

    When would an agent use this?
    - Getting node position for layout calculations or UI rendering
    - Retrieving custom properties set by users or other systems
    - Implementing node selection or highlighting features
    - Saving/loading workflow layout information
    - Debugging node state or configuration issues

    The metadata is separate from the node's functional parameters and doesn't
    affect execution, but provides important context for workflow management.

    Result types:
    - GetNodeMetadataResultSuccess: Returns the metadata dictionary
    - GetNodeMetadataResultFailure: Failed due to node not found

    Args:
        node_name: Name of the node to get metadata for (uses current context node if None)
    """

    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result containing the node's metadata.

    This result provides the metadata dictionary containing non-functional information
    about the node such as position, display properties, and custom user data.

    Common metadata keys include:
    - Position information (x, y coordinates)
    - Display properties (size, color, etc.)
    - User-defined custom properties
    - Creation timestamps or version information

    The workflow is not altered by this read-only operation.

    Args:
        metadata: Dictionary containing the node's metadata
    """

    metadata: dict


@dataclass
@PayloadRegistry.register
class GetNodeMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when metadata retrieval fails.

    This result indicates that the node's metadata could not be retrieved.
    Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)

    When this occurs, the workflow remains unchanged and no metadata information is available.
    """


@dataclass
@PayloadRegistry.register
class SetNodeMetadataRequest(RequestPayload):
    """Request to update metadata associated with a node.

    This request updates the metadata dictionary for a node, which contains information
    like position coordinates, display properties, custom user data, and other
    non-functional attributes. Agents use this to update node presentation and
    store user-defined properties.

    When would an agent use this?
    - Updating node position after user drags or programmatic layout changes
    - Storing custom properties or user annotations on nodes
    - Implementing node styling or appearance modifications
    - Saving user preferences or workflow-specific data
    - Tracking node state or configuration changes

    The metadata is separate from the node's functional parameters and doesn't
    affect execution, but provides important context for workflow management.

    Result types:
    - SetNodeMetadataResultSuccess: Metadata updated successfully
    - SetNodeMetadataResultFailure: Failed due to node not found or update error

    Args:
        metadata: Dictionary containing the new metadata to set
        node_name: Name of the node to update metadata for (uses current context node if None)
    """

    metadata: dict
    # If None is passed, assumes we're using the Node in the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successful result when node metadata is updated.

    This result confirms that the node's metadata was successfully updated.
    The new metadata is now stored with the node and will be returned by
    future GetNodeMetadataRequest operations.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    No return data is provided as the operation is confirmed by success.
    """


@dataclass
@PayloadRegistry.register
class SetNodeMetadataResultFailure(ResultPayloadFailure):
    """Failed result when metadata update fails.

    This result indicates that the node's metadata could not be updated.
    Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)
    - Invalid metadata format or content

    When this occurs, the workflow remains unchanged and the metadata is not updated.
    """


# Get all info via a "jumbo" node event. Batches multiple info requests for, say, a GUI.
# ...jumbode?
@dataclass
@PayloadRegistry.register
class GetAllNodeInfoRequest(RequestPayload):
    """Request to retrieve comprehensive information about a node in a single call.

    This "jumbo" request efficiently batches multiple information requests about a node,
    including metadata, resolution state, connections, and parameter details. Agents use
    this to get a complete picture of a node's state without multiple round trips.

    When would an agent use this?
    - Populating user interfaces that need comprehensive node information
    - Implementing node inspection or debugging features
    - Efficiently gathering complete node state for serialization
    - Optimizing performance by reducing multiple separate requests
    - Getting full context when making decisions about node operations

    This is particularly useful for UIs that need to display node details, as it
    combines what would otherwise be multiple separate requests into one efficient call.

    Result types:
    - GetAllNodeInfoResultSuccess: Returns comprehensive node information
    - GetAllNodeInfoResultFailure: Failed due to node not found or info gathering error

    Args:
        node_name: Name of the node to get information for (uses current context node if None)
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
    """Successful result containing comprehensive node information.

    This result provides a complete snapshot of a node's state, including all
    aspects that would normally require multiple separate requests. This is
    particularly valuable for UI components that need to display detailed node information.

    The workflow is not altered by this read-only operation.

    Args:
        metadata: Node metadata dictionary (position, display properties, etc.)
        node_resolution_state: Current execution state of the node
        connections: All incoming and outgoing connections for the node
        element_id_to_value: Parameter details and values mapped by element ID
        root_node_element: Root element information for the node structure
    """

    metadata: dict
    node_resolution_state: str
    connections: ListConnectionsForNodeResultSuccess
    element_id_to_value: dict[str, ParameterInfoValue]
    root_node_element: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetAllNodeInfoResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when comprehensive node information cannot be retrieved.

    This result indicates that the node's complete information could not be gathered.
    Common failure reasons include:
    - Node not found (invalid node_name or node doesn't exist)
    - No current context node (if node_name is None and no context set)
    - Partial failure in gathering one or more information components

    When this occurs, the workflow remains unchanged and no comprehensive information is available.
    """


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
    """Request payload to serialize a node into a sequence of commands.

    Attributes:
        node_name (str | None): The name of the node to serialize. If None, the node in the current context is used.
        unique_parameter_uuid_to_values (dict[SerializedNodeCommands.UniqueParameterValueUUID, Any]): Mapping of
            UUIDs to unique parameter values. Serialization will check a parameter's value against these, inserting
            new values if necessary. NOTE that it modifies the dict in-place.
        serialized_parameter_value_tracker (SerializedParameterValueTracker): Mapping of hash values to unique parameter
            value UUIDs. If serialization adds new unique values, they are added to this map. Unserializable values
            are preserved to prevent duplicate serialization attempts.
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
    serialized_connection_commands: list[IndirectConnectionSerialization]


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Request to serialize multiple selected nodes into commands.

    This request converts a selection of nodes and their connections into a portable
    command format that can be saved, copied, or transferred. Agents use this for
    implementing copy/paste functionality, workflow export, or backup operations.

    When would an agent use this?
    - Implementing copy/paste functionality for multiple nodes
    - Exporting sections of workflows for reuse
    - Creating workflow templates from existing node groups
    - Backing up or archiving parts of workflows
    - Transferring node configurations between workflows

    The serialization includes both the nodes and their interconnections, preserving
    the complete structure of the selected portion of the workflow.

    Result types:
    - SerializeSelectedNodesToCommandsResultSuccess: Returns serialized commands
    - SerializeSelectedNodesToCommandsResultFailure: Failed due to node not found or serialization error

    Args:
        nodes_to_serialize: List of node name and timestamp pairs to serialize
    """

    # They will be passed with node_name, timestamp
    nodes_to_serialize: list[list[str]]


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Successful result containing serialized commands for selected nodes.

    This result provides the serialized representation of the selected nodes and their
    connections, which can be saved, copied, or transferred to other workflows.

    The serialization preserves the complete structure including node configurations,
    parameter values, and connection relationships.

    The workflow is not altered by this read-only operation.

    Args:
        serialized_selected_node_commands: Complete serialized representation of selected nodes
    """

    # They will be passed with node_name, timestamp
    # Could be a flow command if it's all nodes in a flow.
    serialized_selected_node_commands: SerializedSelectedNodesCommands


@dataclass
@PayloadRegistry.register
class SerializeSelectedNodesToCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when selected nodes cannot be serialized.

    This result indicates that the selected nodes could not be converted to commands.
    Common failure reasons include:
    - One or more nodes in the selection not found
    - Serialization error due to non-serializable parameter values
    - Connection resolution failures
    - Internal serialization logic errors

    When this occurs, the workflow remains unchanged and no serialized commands are available.
    """


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Request to recreate nodes from serialized commands.

    This request takes previously serialized node commands and recreates the nodes
    in the current workflow. Agents use this for implementing paste functionality,
    workflow import, or restoring saved node configurations.

    When would an agent use this?
    - Implementing paste functionality after copy operations
    - Importing node configurations from other workflows
    - Restoring nodes from backup or saved templates
    - Duplicating complex node structures
    - Loading workflow sections from external sources

    The deserialization creates new nodes with unique names and restores their
    parameter values and connections as they existed in the original serialization.

    Result types:
    - DeserializeSelectedNodesFromCommandsResultSuccess: Returns names of created nodes
    - DeserializeSelectedNodesFromCommandsResultFailure: Failed due to deserialization error

    Args:
        positions: Optional list of positions for the recreated nodes
    """

    positions: list[NewPosition] | None = None


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successful result when nodes are recreated from serialized commands.

    This result confirms that the nodes were successfully recreated from the serialized
    commands. The new nodes are now available in the workflow with their parameter
    values and connections restored.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    Args:
        node_names: List of names assigned to the newly created nodes
    """

    node_names: list[str]


@dataclass
@PayloadRegistry.register
class DeserializeSelectedNodesFromCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when nodes cannot be recreated from serialized commands.

    This result indicates that the nodes could not be recreated from the provided commands.
    Common failure reasons include:
    - Invalid or corrupted serialized commands
    - Missing node types or libraries required for deserialization
    - Parameter value deserialization failures
    - Connection creation errors
    - Insufficient resources or constraints

    When this occurs, the workflow remains unchanged and no new nodes are created.
    """


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsRequest(RequestPayload):
    """Request to recreate a single node from serialized commands.

    This request takes previously serialized node commands and recreates the node
    in the current workflow. Agents use this for implementing node restoration,
    template instantiation, or individual node import.

    When would an agent use this?
    - Restoring individual nodes from backups or templates
    - Implementing node-level copy/paste functionality
    - Loading node configurations from external sources
    - Creating nodes from predefined templates
    - Recovering deleted nodes from serialized state

    The deserialization creates a new node with a unique name and restores its
    parameter values as they existed in the original serialization.

    Result types:
    - DeserializeNodeFromCommandsResultSuccess: Returns name of created node
    - DeserializeNodeFromCommandsResultFailure: Failed due to deserialization error

    Args:
        serialized_node_commands: Serialized representation of the node to recreate
    """

    serialized_node_commands: SerializedNodeCommands


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successful result when a node is recreated from serialized commands.

    This result confirms that the node was successfully recreated from the serialized
    commands. The new node is now available in the workflow with its parameter
    values restored.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    Args:
        node_name: Name assigned to the newly created node
    """

    node_name: str


@dataclass
@PayloadRegistry.register
class DeserializeNodeFromCommandsResultFailure(ResultPayloadFailure):
    """Failed result when a node cannot be recreated from serialized commands.

    This result indicates that the node could not be recreated from the provided commands.
    Common failure reasons include:
    - Invalid or corrupted serialized node commands
    - Missing node type or library required for deserialization
    - Parameter value deserialization failures
    - Node creation errors or constraints
    - Insufficient resources or permissions

    When this occurs, the workflow remains unchanged and no new node is created.
    """


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesRequest(WorkflowNotAlteredMixin, RequestPayload):
    """Request to duplicate selected nodes with new positions.

    This request creates copies of the specified nodes, preserving their configuration
    and connections while assigning new names and positions. Agents use this for
    implementing node duplication functionality and workflow expansion.

    When would an agent use this?
    - Implementing duplicate functionality for selected nodes
    - Creating multiple instances of the same node configuration
    - Expanding workflows by replicating useful node patterns
    - Quick copying of nodes without full serialization overhead
    - Building repetitive workflow structures

    The duplication preserves connections between the duplicated nodes while creating
    new unique names for each duplicate.

    Result types:
    - DuplicateSelectedNodesResultSuccess: Returns names of duplicated nodes
    - DuplicateSelectedNodesResultFailure: Failed due to duplication error

    Args:
        nodes_to_duplicate: List of node name and timestamp pairs to duplicate
        positions: Optional list of positions for the duplicated nodes
    """

    nodes_to_duplicate: list[list[str]]
    positions: list[NewPosition] | None = None


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Successful result when nodes are duplicated.

    This result confirms that the nodes were successfully duplicated. The new nodes
    are now available in the workflow with their configuration and connections preserved.

    The workflow is marked as altered, meaning it may need to be saved if persistence is desired.

    Args:
        node_names: List of names assigned to the newly duplicated nodes
    """

    node_names: list[str]


@dataclass
@PayloadRegistry.register
class DuplicateSelectedNodesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed result when nodes cannot be duplicated.

    This result indicates that the nodes could not be duplicated.
    Common failure reasons include:
    - One or more nodes in the selection not found
    - Duplication error due to node constraints or conflicts
    - Insufficient resources or permissions
    - Connection duplication failures

    When this occurs, the workflow remains unchanged and no new nodes are created.
    """
