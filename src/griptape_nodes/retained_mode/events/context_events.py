from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class SetWorkflowContextRequest(RequestPayload):
    """Set the current workflow context.

    Use when: Switching between workflows, initializing workflow sessions,
    setting the active workflow for subsequent operations, workflow navigation.

    Args:
        workflow_name: Name of the workflow to set as current context. When None,
                       the handler mints a fresh "unsaved:<uuid>" registry key and
                       auto-registers an unsaved entry under it. When provided and
                       starting with the unsaved-registry-key prefix ("unsaved:"),
                       the handler auto-registers a fresh unsaved entry keyed by
                       that exact value if one does not already exist.
        display_name: Human-readable name used when auto-registering an unsaved entry.
                      Ignored when the workflow is already in the registry. Defaults to
                      None; in that case the auto-registered entry gets a placeholder
                      name.

    Results: SetWorkflowContextSuccess (carries the resolved workflow_name) |
             SetWorkflowContextFailure (workflow not found)
    """

    workflow_name: str | None = None
    display_name: str | None = None


@dataclass
@PayloadRegistry.register
class SetWorkflowContextSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow context set successfully. Subsequent operations will use this workflow.

    Args:
        workflow_name: Resolved registry key for the workflow now in context. When the
                       request omitted `workflow_name`, this is the freshly minted
                       "unsaved:<uuid>" key. Otherwise it echoes the requested key.
    """

    workflow_name: str = ""


@dataclass
@PayloadRegistry.register
class SetWorkflowContextFailure(WorkflowAlteredMixin, ResultPayloadFailure):
    """Workflow context setting failed. Common causes: workflow not found, invalid workflow name."""


@dataclass
@PayloadRegistry.register
class GetWorkflowContextRequest(RequestPayload):
    """Get the current workflow context.

    Use when: Checking which workflow is active, displaying current workflow info,
    validating workflow state, debugging context issues.

    Results: GetWorkflowContextSuccess (with workflow name) | GetWorkflowContextFailure (no context set)
    """


@dataclass
@PayloadRegistry.register
class GetWorkflowContextSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow context retrieved successfully.

    Args:
        workflow_name: Name of the current workflow context (None if no context set)
    """

    workflow_name: str | None


@dataclass
@PayloadRegistry.register
class GetWorkflowContextFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow context retrieval failed. Common causes: context not initialized, system error."""
