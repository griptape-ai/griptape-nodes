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
                       the handler registers a new unsaved workflow with a fresh workflow
                       id, named "unsaved:<workflow id>". When provided and starting with
                       the unsaved-registry-key prefix ("unsaved:"), the handler registers
                       an unsaved workflow whose id is the rest of the name, if one does
                       not already exist. Any other name must already be registered.
        display_name: Human-readable name used when auto-registering an unsaved entry.
                      Ignored when the workflow is already in the registry. Defaults to
                      None; in that case the auto-registered entry gets a placeholder
                      name.
        working_directory: Folder this workflow belongs to, for a workflow that has no file
                      of its own yet. `{workflow_dir}` -- and so every project directory
                      built on it, `{outputs}` among them -- answers with this until the
                      workflow is saved, at which point the saved file's own directory takes
                      over. A DIRECTORY, not a file path. Absolute paths are recommended;
                      if you supply a relative path it is anchored to the workspace directory
                      (not the project base directory, which may sit one level above). Optional:
                      when None, `{workflow_dir}` answers the folder this workflow's first save
                      would land in, read from the project's `save_workflow` situation.

    Results: SetWorkflowContextSuccess (carries the resolved workflow_name and workflow_id) |
             SetWorkflowContextFailure (workflow not found, working_directory names an
             existing non-directory)
    """

    workflow_name: str | None = None
    display_name: str | None = None
    working_directory: str | None = None


@dataclass
@PayloadRegistry.register
class SetWorkflowContextSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow context set successfully. Subsequent operations will use this workflow.

    Args:
        workflow_name: Resolved registry key for the workflow now in context. When the
                       request omitted `workflow_name`, this is the freshly minted
                       "unsaved:<workflow id>" key. Otherwise it echoes the requested key.
        workflow_id: Permanent id of the workflow now in context.
    """

    workflow_name: str = ""
    workflow_id: str | None = None


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
        is_saved: Whether the current workflow is backed by a file on disk. None when
                  no context is set.
        workflow_id: Permanent id of the current workflow (None if no context set).
    """

    workflow_name: str | None
    is_saved: bool | None = None
    workflow_id: str | None = None


@dataclass
@PayloadRegistry.register
class GetWorkflowContextFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow context retrieval failed. Common causes: context not initialized, system error."""


@dataclass
@PayloadRegistry.register
class EnsureWorkflowAndFlowRequest(RequestPayload):
    """Ensure a workflow + flow context exists, creating scratch ones if needed.

    Use when: Bootstrapping from a cold engine state. This is the typical opening call from
    an MCP client that is about to build a workflow from scratch. Idempotent: if both a
    workflow and a flow are already in the current context, returns their names without
    creating new ones. Only creates the pieces that are missing.

    Args:
        workflow_name: The workflow to enter, or the name for a new one. Ignored when a
            workflow is already in context. A registered name, or one starting with the
            unsaved registry-key prefix ("unsaved:"), is entered as SetWorkflowContextRequest
            enters it. Any other name creates a new unsaved workflow with that display name
            (unless display_name is given). A new workflow is named "unsaved:<workflow id>",
            and that name and the id are returned in the success result.
        display_name: Human-readable name attached to a newly created unsaved workflow.
            Ignored when the workflow is already in context or when a registered
            workflow_name is supplied.
        flow_name: Name to use if a new flow must be created. Ignored when a flow is
            already in context. Defaults to the engine-assigned name.
        working_directory: Folder the workflow belongs to until it is saved, forwarded to
            SetWorkflowContextRequest. Ignored when a workflow is already in context. See
            SetWorkflowContextRequest for what the value means and how it is normalized.

    Results: EnsureWorkflowAndFlowResultSuccess | EnsureWorkflowAndFlowResultFailure
    """

    workflow_name: str | None = None
    display_name: str | None = None
    flow_name: str | None = None
    working_directory: str | None = None


@dataclass
@PayloadRegistry.register
class EnsureWorkflowAndFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow + flow context is ready for subsequent CreateNode calls.

    Args:
        workflow_name: Name of the workflow in the current context.
        flow_name: Name of the flow in the current context.
        created_workflow: True if this call created the workflow; False if an existing one was reused.
        created_flow: True if this call created the flow; False if an existing one was reused.
        workflow_id: Permanent id of the workflow in the current context.
    """

    workflow_name: str
    flow_name: str
    created_workflow: bool
    created_flow: bool
    workflow_id: str | None = None


@dataclass
@PayloadRegistry.register
class EnsureWorkflowAndFlowResultFailure(ResultPayloadFailure):
    """EnsureWorkflowAndFlow failed. Common causes: could not push workflow context, flow creation rejected by the engine."""
