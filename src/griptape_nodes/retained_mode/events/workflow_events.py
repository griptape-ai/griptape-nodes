from dataclasses import dataclass

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryRequest(RequestPayload):
    workflow_name: str
    run_with_clean_slate: bool = True


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RegisterWorkflowRequest(RequestPayload):
    metadata: WorkflowMetadata
    file_name: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowResultSuccess(ResultPayloadSuccess):
    workflow_name: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultSuccess(ResultPayloadSuccess):
    workflows: dict


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteWorkflowRequest(RequestPayload):
    name: str


@dataclass
@PayloadRegistry.register
class DeleteWorkflowResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteWorkflowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RenameWorkflowRequest(RequestPayload):
    workflow_name: str
    requested_name: str


@dataclass
@PayloadRegistry.register
class RenameWorkflowResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RenameWorkflowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SaveWorkflowRequest(RequestPayload):
    file_name: str | None = None


@dataclass
@PayloadRegistry.register
class SaveWorkflowResultSuccess(ResultPayloadSuccess):
    file_path: str


@dataclass
@PayloadRegistry.register
class SaveWorkflowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadata(RequestPayload):
    file_name: str


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultSuccess(ResultPayloadSuccess):
    metadata: WorkflowMetadata


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultFailure(ResultPayloadFailure):
    pass


@dataclass
class SerializedNodeCommands:
    create_node_command: CreateNodeRequest
    parameter_commands: list[RequestPayload]


@dataclass
class SerializedFlowCommands:
    @dataclass
    class IndexedConnectionSerialization:
        # Companion class to create connections from node indices, since we can't predict the names.
        # These are indices into the SerializeNodeCommandsRequest list we maintain.
        source_node_index: int
        source_parameter_name: str
        target_node_index: int
        target_parameter_name: str

    create_flow_command: CreateFlowRequest
    serialized_node_commands: list[SerializedNodeCommands]
    serialized_connections: list[IndexedConnectionSerialization]
    sub_flows_commands: list["SerializedFlowCommands"]


@dataclass
@PayloadRegistry.register
class SerializeNodeCommandsRequest(RequestPayload):
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class SerializeNodeCommandsResultSuccess(ResultPayloadSuccess):
    serialized_node_commands: SerializedNodeCommands


@dataclass
@PayloadRegistry.register
class SerializeNodeCommandsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SerializeFlowCommandsRequest(RequestPayload):
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class SerializeFlowCommandsResultSuccess(ResultPayloadSuccess):
    serialized_flow_commands: SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class SerializeFlowCommandsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SerializeWorkflowCommandsRequest(RequestPayload):
    workflow_name: str


@dataclass
@PayloadRegistry.register
class SerializeWorkflowCommandsResultSuccess(ResultPayloadSuccess):
    library_requests: list[RegisterLibraryFromFileRequest]
    flow_request: SerializeFlowCommandsRequest
