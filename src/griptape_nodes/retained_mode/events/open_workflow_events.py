"""Requests that open, list, and close the workflows an engine holds at once.

Every open workflow has a `workflow_id`, stable for as long as it stays open, through saves, renames,
moves, and library reloads. A workflow request names one in its own `workflow_id` to act on that
workflow; see `WorkflowRequest`. The engine has no "active" workflow: which one a client shows is the
client's business.
"""

from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    HostRequest,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
    WorkflowRequest,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class OpenWorkflowRequest(HostRequest):
    """Open a workflow alongside the ones already open.

    Use when: Opening a saved workflow, or starting a new one, without closing the workflows already open.

    With `workflow_name`, opens that workflow from the registry, running a saved one's file to build it.
    A workflow that is already open stays as it is, and its id is returned. Without `workflow_name`,
    starts a new unsaved workflow with an empty flow.

    Name the returned id on the workflow requests meant for it. With several workflows open, a workflow
    request that names none fails.

    Args:
        workflow_name: Registry key of the workflow to open, or None to start a new one.
        display_name: For a new workflow, its name as users see it.
        working_directory: For a new workflow, the folder it belongs to until it is saved. See
            SetWorkflowContextRequest.

    Results: OpenWorkflowResultSuccess | OpenWorkflowResultFailure (not in the registry, or failed to load)
    """

    workflow_name: str | None = None
    display_name: str | None = None
    working_directory: str | None = None


@dataclass
@PayloadRegistry.register
class OpenWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The workflow is open.

    Args:
        workflow_id: The id to address the workflow by while it stays open.
        workflow_name: Its registry key. For a new workflow, the "unsaved:<uuid>" key minted for it.
        already_open: True when the workflow was already open and nothing was loaded.
    """

    workflow_id: str
    workflow_name: str
    already_open: bool


@dataclass
@PayloadRegistry.register
class OpenWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Opening the workflow failed. The workflows already open are unchanged."""


@dataclass
class OpenWorkflow:
    """One workflow the engine holds open.

    Args:
        workflow_id: The id to address it by.
        workflow_name: Its registry key.
        display_name: Its name as users see it.
        is_running: Whether it is running.
    """

    workflow_id: str
    workflow_name: str
    display_name: str
    is_running: bool


@dataclass
@PayloadRegistry.register
class ListOpenWorkflowsRequest(HostRequest):
    """List the workflows the engine holds open.

    Use when: Showing which workflows can be switched to without reloading, and which one is running.

    Results: ListOpenWorkflowsResultSuccess
    """


@dataclass
@PayloadRegistry.register
class ListOpenWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The open workflows.

    Args:
        workflows: The open workflows, in the order they were opened.
    """

    workflows: list[OpenWorkflow]


@dataclass
@PayloadRegistry.register
class ListOpenWorkflowsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Listing the open workflows failed."""


@dataclass
@PayloadRegistry.register
class CloseWorkflowRequest(WorkflowRequest):
    """Close the workflow this request acts on, discarding its unsaved changes.

    Use when: The user closes a workflow they have open. Name it in `workflow_id`.

    Cancels its run if it has one.

    Results: CloseWorkflowResultSuccess | CloseWorkflowResultFailure (it couldn't be cleared)
    """


@dataclass
@PayloadRegistry.register
class CloseWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The workflow is closed."""


@dataclass
@PayloadRegistry.register
class CloseWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Closing the workflow failed."""


@dataclass
@PayloadRegistry.register
class OpenWorkflowsChanged(AppPayload):
    """A workflow was opened, closed, renamed, or rebuilt, so a client listing them should list them again.

    Sent for every change, including those no client asked for, such as a library reload rebuilding them
    or clearing all object state closing them.
    """
