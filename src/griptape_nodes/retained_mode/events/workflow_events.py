from dataclasses import dataclass

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
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
class SaveSceneRequest(RequestPayload):
    file_name: str | None = None


@dataclass
@PayloadRegistry.register
class SaveSceneResultSuccess(ResultPayloadSuccess):
    file_path: str


@dataclass
@PayloadRegistry.register
class SaveSceneResultFailure(ResultPayloadFailure):
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
