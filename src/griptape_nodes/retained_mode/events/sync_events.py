from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class StartSyncAllCloudWorkflowsRequest(RequestPayload):
    """Start syncing all cloud workflows to local synced_workflows directory.

    Use when: Initiating download of all workflow files from cloud storage, keeping local sync directory updated,
    preparing for offline workflow development, backing up cloud workflows locally.

    Results: StartSyncAllCloudWorkflowsResultSuccess (sync started) | StartSyncAllCloudWorkflowsResultFailure (failed to start)
    """


@dataclass
@PayloadRegistry.register
class StartSyncAllCloudWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Cloud workflow sync started successfully.

    Args:
        sync_directory: Path to the local sync directory where files will be saved
        total_workflows: Number of workflows that will be synced
    """

    sync_directory: str
    total_workflows: int


@dataclass
@PayloadRegistry.register
class StartSyncAllCloudWorkflowsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Cloud workflow sync failed to start. Common causes: cloud not configured, network error, storage error, permission denied."""


@dataclass
@PayloadRegistry.register
class ListCloudWorkflowsRequest(RequestPayload):
    """List all workflow files available in cloud storage.

    Use when: Browsing available cloud workflows, checking what's available to sync,
    workflow discovery, validating cloud storage contents.

    Results: ListCloudWorkflowsResultSuccess (with workflow list) | ListCloudWorkflowsResultFailure (list error)
    """


@dataclass
@PayloadRegistry.register
class ListCloudWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Cloud workflows listed successfully.

    Args:
        workflows: List of workflow information from cloud storage (filename, size, modified date)
    """

    workflows: list[dict]


@dataclass
@PayloadRegistry.register
class ListCloudWorkflowsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Cloud workflows listing failed. Common causes: cloud not configured, network error, storage error."""
