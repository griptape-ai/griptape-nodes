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
from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass(kw_only=True)
@PayloadRegistry.register
class CreateFlowRequest(RequestPayload):
    parent_flow_name: str | None
    flow_name: str | None = None
    # When True, this Flow will be pushed as the new Current Context.
    set_as_new_context: bool = True


@dataclass
@PayloadRegistry.register
class CreateFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    flow_name: str


@dataclass
@PayloadRegistry.register
class CreateFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowRequest(RequestPayload):
    # If None is passed, assumes we're deleting the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class DeleteFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListNodesInFlowRequest(RequestPayload):
    # If None is passed, assumes we're using the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    node_names: list[str]


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


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
    @dataclass
    class IndexedConnectionSerialization:
        """Companion class to create connections from node indices, since we can't predict the names.

        These are indices into the SerializeNodeCommandsRequest list we maintain.
        """

        source_node_index: int
        source_parameter_name: str
        target_node_index: int
        target_parameter_name: str

    # Which node libraries are in use by this flow (includes child flows)
    node_libraries_used: set[LibraryNameAndVersion]

    # The command to create the flow that contains all of this.
    create_flow_command: CreateFlowRequest

    # Handles creating all of the nodes themselves, along with configuring them.
    # Does NOT set Parameter values, which is done as a separate step.
    serialized_node_commands: list[SerializedNodeCommands]

    # Creates the connections between Nodes.
    serialized_connections: list[IndexedConnectionSerialization]

    # Records the unique Parameter values used by the Flow.
    unique_parameter_values: list[Any]

    # The parameter value assignment commands used when deserializing.
    set_parameter_value_commands: list[list[SerializedNodeCommands.IndexedSetParameterValueCommand]]

    # Cascades into sub-flows within this serialization.
    sub_flows_commands: list["SerializedFlowCommands"]


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsRequest(RequestPayload):
    # If None is passed, assumes we're serializing the flow in the Current Context.
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsResultSuccess(ResultPayloadSuccess):
    serialized_flow_commands: SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class SerializeFlowToCommandsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsRequest(RequestPayload):
    serialized_flow_commands: SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsResultSuccess(ResultPayloadSuccess):
    flow_name: str


@dataclass
@PayloadRegistry.register
class DeserializeFlowFromCommandsResultFailure(ResultPayloadFailure):
    pass
