from pydantic.dataclasses import dataclass

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@PayloadRegistry.register
class RunWorkflowFromScratchRequest(RequestPayload):
    file_path: str


@PayloadRegistry.register
class RunWorkflowFromScratchResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class RunWorkflowFromScratchResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RunWorkflowWithCurrentStateRequest(RequestPayload):
    file_path: str


@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RunWorkflowFromRegistryRequest(RequestPayload):
    workflow_name: str
    run_with_clean_slate: bool = True


@PayloadRegistry.register
class RunWorkflowFromRegistryResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class RunWorkflowFromRegistryResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RegisterWorkflowRequest(RequestPayload):
    metadata: WorkflowMetadata
    file_name: str


@PayloadRegistry.register
class RegisterWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    workflow_name: str


@PayloadRegistry.register
class RegisterWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class ListAllWorkflowsRequest(RequestPayload):
    pass


@PayloadRegistry.register
class ListAllWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    workflows: dict


@PayloadRegistry.register
class ListAllWorkflowsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class DeleteWorkflowRequest(RequestPayload):
    name: str


@PayloadRegistry.register
class DeleteWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class DeleteWorkflowResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class RenameWorkflowRequest(RequestPayload):
    workflow_name: str
    requested_name: str


@PayloadRegistry.register
class RenameWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@PayloadRegistry.register
class RenameWorkflowResultFailure(ResultPayloadFailure):
    pass


@PayloadRegistry.register
class SaveWorkflowRequest(RequestPayload):
    file_name: str | None = None


@PayloadRegistry.register
class SaveWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    file_path: str


@PayloadRegistry.register
class SaveWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class LoadWorkflowMetadata(RequestPayload):
    file_name: str


@PayloadRegistry.register
class LoadWorkflowMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    metadata: WorkflowMetadata


@PayloadRegistry.register
class LoadWorkflowMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@PayloadRegistry.register
class PublishWorkflowRequest(RequestPayload):
    workflow_name: str


@PayloadRegistry.register
class PublishWorkflowResultSuccess(ResultPayloadSuccess):
    workflow_id: str


@PayloadRegistry.register
class PublishWorkflowResultFailure(ResultPayloadFailure):
    pass
