from dataclasses import dataclass

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadFailureUnalteredWorkflow,
    ResultPayloadSuccessAlteredWorkflow,
    ResultPayloadSuccessUnalteredWorkflow,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchRequest(RequestPayload):
    file_path: str


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class RunWorkflowWithCurrentStateResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class RunWorkflowFromRegistryResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class RegisterWorkflowResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    workflow_name: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    workflows: dict


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class DeleteWorkflowRequest(RequestPayload):
    name: str


@dataclass
@PayloadRegistry.register
class DeleteWorkflowResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class RenameWorkflowResultSuccess(ResultPayloadSuccessAlteredWorkflow):
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
class SaveWorkflowResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    file_path: str


@dataclass
@PayloadRegistry.register
class SaveWorkflowResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadata(RequestPayload):
    file_name: str


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultSuccess(ResultPayloadSuccessUnalteredWorkflow):
    metadata: WorkflowMetadata


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultFailure(ResultPayloadFailureUnalteredWorkflow):
    pass
