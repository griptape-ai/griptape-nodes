from dataclasses import dataclass
from typing import Any

from griptape_nodes.node_library.library_registry import LibraryNameAndVersion
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands, SetLockNodeStateRequest
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.events.workflow_events import ImportWorkflowAsReferencedSubFlowRequest


@dataclass(kw_only=True)
@PayloadRegistry.register
class CreateFlowRequest(RequestPayload):
    """Create a new flow (sub-workflow) within a parent flow.

    Use when: Creating sub-workflows, organizing complex workflows into components,
    implementing reusable workflow patterns, building hierarchical workflows.

    Args:
        parent_flow_name: Name of the parent flow to create the new flow within
        flow_name: Name for the new flow (None for auto-generated)
        set_as_new_context: Whether to set this flow as the new current context
        metadata: Initial metadata for the flow

    Results: CreateFlowResultSuccess (with flow name) | CreateFlowResultFailure (parent not found, name conflicts)
    """

    parent_flow_name: str | None
    flow_name: str | None = None
    # When True, this Flow will be pushed as the new Current Context.
    set_as_new_context: bool = True
    metadata: dict | None = None


@dataclass
@PayloadRegistry.register
class CreateFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow created successfully.

    Args:
        flow_name: Name assigned to the new flow
    """

    flow_name: str


@dataclass
@PayloadRegistry.register
class CreateFlowResultFailure(ResultPayloadFailure):
    """Flow creation failed. Common causes: parent flow not found, name conflicts, invalid parameters."""


@dataclass
@PayloadRegistry.register
class DeleteFlowRequest(RequestPayload):
    """Delete a flow and all its contents.

    Use when: Removing unused sub-workflows, cleaning up complex workflows,
    implementing flow management features. Cascades to delete all nodes and sub-flows.

    Args:
        flow_name: Name of the flow to delete (None for current context flow)

    Results: DeleteFlowResultSuccess | DeleteFlowResultFailure (flow not found, deletion not allowed)
    """

    # If None is passed, assumes we're deleting the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow deleted successfully. All nodes and sub-flows removed."""


@dataclass
@PayloadRegistry.register
class DeleteFlowResultFailure(ResultPayloadFailure):
    """Flow deletion failed. Common causes: flow not found, no current context, deletion not allowed."""


@dataclass
@PayloadRegistry.register
class ListNodesInFlowRequest(RequestPayload):
    """List all nodes in a specific flow.

    Use when: Inspecting flow contents, building flow visualizations,
    implementing flow management features, debugging workflow structure.

    Args:
        flow_name: Name of the flow to list nodes from (None for current context flow)

    Results: ListNodesInFlowResultSuccess (with node names) | ListNodesInFlowResultFailure (flow not found)
    """

    # If None is passed, assumes we're using the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Flow nodes listed successfully.

    Args:
        node_names: List of node names in the flow
    """

    node_names: list[str]


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow nodes listing failed. Common causes: flow not found, no current context."""


# We have two different ways to list flows:
# 1. ListFlowsInFlowRequest - List flows in a specific flow, or if parent_flow_name=None, list canvas/top-level flows
# 2. ListFlowsInCurrentContext - List flows in whatever flow is at the top of the Current Context
# These are separate classes to avoid ambiguity and to catch incorrect usage at compile time.
# It was implemented this way to maintain backwards compatibility with the editor.
@dataclass
@PayloadRegistry.register
class ListFlowsInCurrentContextRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListFlowsInCurrentContextResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    flow_names: list[str]


@dataclass
@PayloadRegistry.register
class ListFlowsInCurrentContextResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# Gives a list of the flows directly parented by the node specified.
@dataclass
@PayloadRegistry.register
class ListFlowsInFlowRequest(RequestPayload):
    # Pass in None to get the canvas.
    parent_flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    flow_names: list[str]


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetTopLevelFlowRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetTopLevelFlowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    flow_name: str | None


# A Flow's state can be serialized into a sequence of commands that the engine then runs.
@dataclass
class SerializedFlowCommands:
    """Represents the serialized commands for a flow, including the nodes and their connections.

    Useful for save/load, copy/paste, etc.

    Attributes:
        node_libraries_used (set[LibraryNameAndVersion]): Set of libraries and versions used by the nodes,
            including those in child flows.
        flow_initialization_command (CreateFlowRequest | ImportWorkflowAsReferencedSubFlowRequest | None): Command to initialize the flow that contains all of this.
            Can be CreateFlowRequest for standalone flows, ImportWorkflowAsReferencedSubFlowRequest for referenced workflows,
            or None to deserialize into whatever Flow is in the Current Context.
        serialized_node_commands (list[SerializedNodeCommands]): List of serialized commands for nodes.
            Handles creating all of the nodes themselves, along with configuring them. Does NOT set Parameter values,
            which is done as a separate step.
        serialized_connections (list[SerializedFlowCommands.IndirectConnectionSerialization]): List of serialized connections.
            Creates the connections between Nodes.
        unique_parameter_uuid_to_values (dict[SerializedNodeCommands.UniqueParameterValueUUID, Any]): Records the unique Parameter values used by the Flow.
        set_parameter_value_commands (dict[SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]]): List of commands
            to set parameter values, keyed by node UUID, during deserialization.
        sub_flows_commands (list["SerializedFlowCommands"]): List of sub-flow commands. Cascades into sub-flows within this serialization.
        referenced_workflows (set[str]): Set of workflow file paths that are referenced by this flow and its sub-flows.
            Used for validation before deserialization to ensure all referenced workflows are available.
    """

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

    node_libraries_used: set[LibraryNameAndVersion]
    flow_initialization_command: CreateFlowRequest | ImportWorkflowAsReferencedSubFlowRequest | None
    serialized_node_commands: list[SerializedNodeCommands]
    serialized_connections: list[IndirectConnectionSerialization]
    unique_parameter_uuid_to_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any]
    set_parameter_value_commands: dict[
        SerializedNodeCommands.NodeUUID, list[SerializedNodeCommands.IndirectSetParameterValueCommand]
    ]
    set_lock_commands_per_node: dict[SerializedNodeCommands.NodeUUID, SetLockNodeStateRequest]
    sub_flows_commands: list["SerializedFlowCommands"]
    referenced_workflows: set[str]


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsRequest(RequestPayload):
    """Request payload to serialize a flow into a sequence of commands.

    Attributes:
        flow_name (str | None): The name of the flow to serialize. If None is passed, assumes we're serializing the flow in the Current Context.
        include_create_flow_command (bool): If set to False, this will omit the CreateFlow call from the serialized flow object.
            This can be useful so that the contents of a flow can be deserialized into an existing flow instead of creating a new one and deserializing the nodes into that.
            Copy/paste can make use of this.
    """

    flow_name: str | None = None
    include_create_flow_command: bool = True


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    serialized_flow_commands: SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsRequest(RequestPayload):
    serialized_flow_commands: SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    flow_name: str


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetFlowDetailsRequest(RequestPayload):
    """Request payload to get detailed information about a flow.

    This provides metadata about a flow including its reference status and parent hierarchy,
    useful for editor integration to display flows appropriately.

    Attributes:
        flow_name (str | None): The name of the flow to get details for. If None is passed,
            assumes we're getting details for the flow in the Current Context.
    """

    # If None is passed, assumes we're getting details for the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetFlowDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Success result containing flow details.

    Attributes:
        referenced_workflow_name (str | None): The name of the workflow that was
            imported to create this flow. None if this flow was created standalone.
        parent_flow_name (str | None): The name of the parent flow, or None if this is a
            top-level flow.
    """

    referenced_workflow_name: str | None
    parent_flow_name: str | None


@dataclass
@PayloadRegistry.register
class GetFlowDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failure result when flow details cannot be retrieved.

    This occurs when the specified flow doesn't exist, the current context is empty
    (when flow_name is None), or there are issues with the flow's parent mapping.
    """


@dataclass
@PayloadRegistry.register
class GetFlowMetadataRequest(RequestPayload):
    """Get metadata associated with a flow.

    Use when: Retrieving flow layout information, getting custom flow properties,
    implementing flow management features, debugging flow state.

    Results: GetFlowMetadataResultSuccess (with metadata dict) | GetFlowMetadataResultFailure (flow not found)
    """

    # If None is passed, assumes we're using the Flow in the Current Context
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetFlowMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Flow metadata retrieved successfully.

    Args:
        metadata: Dictionary containing flow metadata
    """

    metadata: dict


@dataclass
@PayloadRegistry.register
class GetFlowMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow metadata retrieval failed. Common causes: flow not found, no current context."""


@dataclass
@PayloadRegistry.register
class SetFlowMetadataRequest(RequestPayload):
    """Set metadata associated with a flow.

    Use when: Updating flow layout information, storing custom flow properties,
    implementing flow management features, saving flow state.

    Results: SetFlowMetadataResultSuccess | SetFlowMetadataResultFailure (flow not found, metadata error)
    """

    metadata: dict
    # If None is passed, assumes we're using the Flow in the Current Context
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetFlowMetadataResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Flow metadata updated successfully."""


@dataclass
@PayloadRegistry.register
class SetFlowMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Flow metadata update failed. Common causes: flow not found, no current context, invalid metadata."""
