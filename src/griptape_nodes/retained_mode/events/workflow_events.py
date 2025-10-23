from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from griptape_nodes.node_library.workflow_registry import WorkflowMetadata, WorkflowShape
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.execution_events import ExecutionPayload
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.flow_events import SerializedFlowCommands


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchRequest(RequestPayload):
    """Run a workflow from file, starting with a clean state.

    Use when: Loading and executing saved workflows, testing workflows from files,
    running workflows in clean environments, batch processing workflows.

    Args:
        file_path: Path to the workflow file to load and execute

    Results: RunWorkflowFromScratchResultSuccess | RunWorkflowFromScratchResultFailure (file not found, load error)
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchResultSuccess(ResultPayloadSuccess):
    """Workflow loaded and started successfully from file."""


@dataclass
@PayloadRegistry.register
class RunWorkflowFromScratchResultFailure(ResultPayloadFailure):
    """Workflow execution from file failed. Common causes: file not found, invalid workflow format, load error."""


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateRequest(RequestPayload):
    """Run a workflow from file, preserving current state.

    Use when: Loading workflows while keeping existing node values, updating workflow structure
    without losing progress, iterative workflow development.

    Args:
        file_path: Path to the workflow file to load while preserving current state

    Results: RunWorkflowWithCurrentStateResultSuccess | RunWorkflowWithCurrentStateResultFailure (file not found, merge error)
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow loaded successfully while preserving current state."""


@dataclass
@PayloadRegistry.register
class RunWorkflowWithCurrentStateResultFailure(ResultPayloadFailure):
    """Workflow execution with current state failed. Common causes: file not found, state merge conflict, load error."""


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryRequest(RequestPayload):
    """Run a workflow from the registry.

    Use when: Executing registered workflows, running workflows by name,
    using workflow templates, automated workflow execution.

    Args:
        workflow_name: Name of the workflow in the registry to execute
        run_with_clean_slate: Whether to start with a clean state (default: True)

    Results: RunWorkflowFromRegistryResultSuccess | RunWorkflowFromRegistryResultFailure (workflow not found, execution error)
    """

    workflow_name: str
    run_with_clean_slate: bool = True


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryResultSuccess(ResultPayloadSuccess):
    """Workflow from registry started successfully."""


@dataclass
@PayloadRegistry.register
class RunWorkflowFromRegistryResultFailure(ResultPayloadFailure):
    """Workflow execution from registry failed. Common causes: workflow not found, execution error, registry error."""


@dataclass
@PayloadRegistry.register
class RegisterWorkflowRequest(RequestPayload):
    """Register a workflow in the registry.

    Use when: Publishing workflows for reuse, creating workflow templates,
    managing workflow libraries, making workflows available by name.

    Args:
        metadata: Workflow metadata containing name, description, and other properties
        file_name: Name of the workflow file to register

    Results: RegisterWorkflowResultSuccess (with workflow name) | RegisterWorkflowResultFailure (registration error)
    """

    metadata: WorkflowMetadata
    file_name: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow registered successfully.

    Args:
        workflow_name: Name assigned to the registered workflow
    """

    workflow_name: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow registration failed. Common causes: invalid metadata, file not found, name conflict."""


@dataclass
@PayloadRegistry.register
class ImportWorkflowRequest(RequestPayload):
    """Import and register a workflow from a file.

    Use when: Importing workflows from external sources, batch workflow imports,
    command-line workflow registration, loading workflows from shared locations.

    Args:
        file_path: Path to the workflow file to import and register

    Results: ImportWorkflowResultSuccess (with workflow name) | ImportWorkflowResultFailure (import error)
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class ImportWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow imported and registered successfully.

    Args:
        workflow_name: Name of the imported workflow
    """

    workflow_name: str


@dataclass
@PayloadRegistry.register
class ImportWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow import failed. Common causes: file not found, invalid workflow format, metadata extraction error, registration error."""


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsRequest(RequestPayload):
    """List all workflows in the registry.

    Use when: Displaying workflow catalogs, browsing available workflows,
    implementing workflow selection UIs, workflow management.

    Results: ListAllWorkflowsResultSuccess (with workflows dict) | ListAllWorkflowsResultFailure (registry error)
    """


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflows listed successfully.

    Args:
        workflows: Dictionary of workflow names to metadata
    """

    workflows: dict


@dataclass
@PayloadRegistry.register
class ListAllWorkflowsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow listing failed. Common causes: registry not initialized, registry error."""


@dataclass
@PayloadRegistry.register
class DeleteWorkflowRequest(RequestPayload):
    """Delete a workflow from the registry.

    Use when: Removing obsolete workflows, cleaning up workflow libraries,
    unregistering workflows, workflow management.

    Args:
        name: Name of the workflow to delete from the registry

    Results: DeleteWorkflowResultSuccess | DeleteWorkflowResultFailure (workflow not found, deletion error)
    """

    name: str


@dataclass
@PayloadRegistry.register
class DeleteWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow deleted successfully from registry."""


@dataclass
@PayloadRegistry.register
class DeleteWorkflowResultFailure(ResultPayloadFailure):
    """Workflow deletion failed. Common causes: workflow not found, deletion not allowed, registry error."""


@dataclass
@PayloadRegistry.register
class RenameWorkflowRequest(RequestPayload):
    """Rename a workflow in the registry.

    Use when: Updating workflow names, organizing workflow libraries,
    fixing naming conflicts, workflow management.

    Args:
        workflow_name: Current name of the workflow
        requested_name: New name for the workflow

    Results: RenameWorkflowResultSuccess | RenameWorkflowResultFailure (workflow not found, name conflict)
    """

    workflow_name: str
    requested_name: str


@dataclass
@PayloadRegistry.register
class RenameWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow renamed successfully."""


@dataclass
@PayloadRegistry.register
class RenameWorkflowResultFailure(ResultPayloadFailure):
    """Workflow rename failed. Common causes: workflow not found, name already exists, invalid name."""


@dataclass
@PayloadRegistry.register
class SaveWorkflowRequest(RequestPayload):
    """Save the current workflow to a file.

    Use when: Persisting workflow changes, creating workflow backups,
    exporting workflows, saving before major changes.

    Args:
        file_name: Name of the file to save the workflow to (None for auto-generated)
        image_path: Path to save workflow image/thumbnail (None for no image)
        pickle_control_flow_result: Whether to use pickle-based serialization for control flow results (None for default behavior)

    Results: SaveWorkflowResultSuccess (with file path) | SaveWorkflowResultFailure (save error)
    """

    file_name: str | None = None
    image_path: str | None = None
    pickle_control_flow_result: bool | None = None


@dataclass
@PayloadRegistry.register
class ImportWorkflowAsReferencedSubFlowRequest(RequestPayload):
    """Import a workflow as a referenced sub-flow.

    Use when: Reusing workflows as components, creating modular workflows,
    importing workflow templates, building composite workflows.

    Results: ImportWorkflowAsReferencedSubFlowResultSuccess (with flow name) | ImportWorkflowAsReferencedSubFlowResultFailure (import error)
    """

    workflow_name: str
    flow_name: str | None = None  # If None, import into current context flow
    imported_flow_metadata: dict | None = None  # Metadata to apply to the imported flow


@dataclass
@PayloadRegistry.register
class ImportWorkflowAsReferencedSubFlowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow imported successfully as referenced sub-flow.

    Args:
        created_flow_name: Name of the created sub-flow
    """

    created_flow_name: str


@dataclass
@PayloadRegistry.register
class ImportWorkflowAsReferencedSubFlowResultFailure(ResultPayloadFailure):
    """Workflow import as sub-flow failed. Common causes: workflow not found, import error, name conflict."""


@dataclass
@PayloadRegistry.register
class SaveWorkflowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow saved successfully.

    Args:
        file_path: Path where the workflow was saved
    """

    file_path: str


@dataclass
@PayloadRegistry.register
class SaveWorkflowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow save failed. Common causes: file system error, permission denied, invalid path."""


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadata(RequestPayload):
    """Load workflow metadata from a file.

    Use when: Inspecting workflow properties, validating workflow files,
    displaying workflow information, workflow management.

    Args:
        file_name: Name of the workflow file to load metadata from

    Results: LoadWorkflowMetadataResultSuccess (with metadata) | LoadWorkflowMetadataResultFailure (load error)
    """

    file_name: str


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow metadata loaded successfully.

    Args:
        metadata: Workflow metadata object
    """

    metadata: WorkflowMetadata


@dataclass
@PayloadRegistry.register
class LoadWorkflowMetadataResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow metadata load failed. Common causes: file not found, invalid format, parse error."""


@dataclass
@PayloadRegistry.register
class PublishWorkflowRequest(RequestPayload):
    """Publish a workflow for distribution.

    Use when: Sharing workflows with others, creating workflow packages,
    distributing workflow templates, workflow publishing.

    Results: PublishWorkflowResultSuccess (with file path) | PublishWorkflowResultFailure (publish error)
    """

    workflow_name: str
    publisher_name: str
    # This can be removed after GUI release
    execute_on_publish: bool | None = None
    published_workflow_file_name: str | None = None
    pickle_control_flow_result: bool = False
    metadata: dict | None = None


@dataclass
@PayloadRegistry.register
class PublishWorkflowResultSuccess(ResultPayloadSuccess):
    """Workflow published successfully.

    Args:
        published_workflow_file_path: Path to the published workflow file
    """

    published_workflow_file_path: str
    metadata: dict | None = None


@dataclass
@PayloadRegistry.register
class PublishWorkflowResultFailure(ResultPayloadFailure):
    """Workflow publish failed. Common causes: workflow not found, publish error, file system error."""


@dataclass
@PayloadRegistry.register
class PublishWorkflowProgressEvent(ExecutionPayload):
    """Event emitted to indicate progress during workflow publishing.

    Args:
        progress: Progress percentage (0-100)
        message: Optional progress message
    """

    progress: float
    message: str | None = None


@dataclass
@PayloadRegistry.register
class BranchWorkflowRequest(RequestPayload):
    """Create a branch (copy) of an existing workflow with branch tracking.

    Use when: Creating workflow variants, branching workflows for experimentation,
    creating personal copies of shared workflows, preparing for workflow collaboration.

    Args:
        workflow_name: Name of the workflow to branch
        branched_workflow_name: Name for the branched workflow (None for auto-generated)

    Results: BranchWorkflowResultSuccess (with branch name) | BranchWorkflowResultFailure (branch error)
    """

    workflow_name: str
    branched_workflow_name: str | None = None


@dataclass
@PayloadRegistry.register
class BranchWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow branched successfully.

    Args:
        branched_workflow_name: Name of the created branch
        original_workflow_name: Name of the original workflow
    """

    branched_workflow_name: str
    original_workflow_name: str


@dataclass
@PayloadRegistry.register
class BranchWorkflowResultFailure(ResultPayloadFailure):
    """Workflow branch failed. Common causes: workflow not found, name conflict, save error."""


@dataclass
@PayloadRegistry.register
class MergeWorkflowBranchRequest(RequestPayload):
    """Merge a branch back into its source workflow, removing the branch when complete.

    Use when: Integrating branch changes back into the original workflow, consolidating
    successful branch experiments, applying approved branch modifications to source.

    Args:
        workflow_name: Name of the branch workflow to merge back into its source

    Results: MergeWorkflowBranchResultSuccess (with merge details) | MergeWorkflowBranchResultFailure (merge error)
    """

    workflow_name: str


@dataclass
@PayloadRegistry.register
class MergeWorkflowBranchResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Branch merge back to source completed successfully.

    Args:
        merged_workflow_name: Name of the source workflow after merge
    """

    merged_workflow_name: str


@dataclass
@PayloadRegistry.register
class MergeWorkflowBranchResultFailure(ResultPayloadFailure):
    """Workflow branch merge failed."""


@dataclass
@PayloadRegistry.register
class ResetWorkflowBranchRequest(RequestPayload):
    """Reset a branch to match its source workflow, discarding branch changes.

    Use when: Discarding branch modifications, reverting branch to source state,
    abandoning branch experiments, syncing branch with latest source changes.

    Args:
        workflow_name: Name of the branch workflow to reset to its source

    Results: ResetWorkflowBranchResultSuccess (with reset details) | ResetWorkflowBranchResultFailure (reset error)
    """

    workflow_name: str


@dataclass
@PayloadRegistry.register
class ResetWorkflowBranchResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Branch reset to source completed successfully.

    Args:
        reset_workflow_name: Name of the branch workflow after reset
    """

    reset_workflow_name: str


@dataclass
@PayloadRegistry.register
class ResetWorkflowBranchResultFailure(ResultPayloadFailure):
    """Workflow branch reset failed. Common causes: workflows not branch-related, reset conflict, save error."""


@dataclass
@PayloadRegistry.register
class CompareWorkflowsRequest(RequestPayload):
    """Compare two workflows to determine if one is ahead, behind, or up-to-date relative to the other.

    Use when: Checking if branched workflows need updates, determining if local changes exist,
    managing workflow synchronization, preparing for merge operations.

    Args:
        workflow_name: Name of the workflow to evaluate
        compare_workflow_name: Name of the workflow to compare against

    Results: CompareWorkflowsResultSuccess (with status details) | CompareWorkflowsResultFailure (evaluation error)
    """

    workflow_name: str
    compare_workflow_name: str


@dataclass
@PayloadRegistry.register
class CompareWorkflowsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow comparison completed successfully.

    Args:
        workflow_name: Name of the evaluated workflow
        compare_workflow_name: Name of the workflow being compared against (if any)
        status: Status relative to source - "up_to_date", "ahead", "behind", "diverged", or "no_source"
        workflow_last_modified: Last modified timestamp of the workflow
        source_last_modified: Last modified timestamp of the source (if exists)
        details: Additional details about the comparison
    """

    workflow_name: str
    compare_workflow_name: str | None
    status: Literal["up_to_date", "ahead", "behind", "diverged", "no_source"]
    workflow_last_modified: str | None
    source_last_modified: str | None
    details: str


@dataclass
@PayloadRegistry.register
class CompareWorkflowsResultFailure(ResultPayloadFailure):
    """Workflow comparison failed. Common causes: workflow not found, source not accessible, comparison error."""


@dataclass
@PayloadRegistry.register
class MoveWorkflowRequest(RequestPayload):
    """Move a workflow to a different directory in the workspace.

    Use when: Organizing workflows into directories, restructuring workflow hierarchies,
    moving workflows to categorized folders, cleaning up workspace organization.

    Args:
        workflow_name: Name of the workflow to move
        target_directory: Target directory path relative to workspace root

    Results: MoveWorkflowResultSuccess (with new path) | MoveWorkflowResultFailure (move error)
    """

    workflow_name: str
    target_directory: str


@dataclass
@PayloadRegistry.register
class MoveWorkflowResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Workflow moved successfully.

    Args:
        moved_file_path: New file path after the move
    """

    moved_file_path: str


@dataclass
@PayloadRegistry.register
class MoveWorkflowResultFailure(ResultPayloadFailure):
    """Workflow move failed. Common causes: workflow not found, invalid target directory, file system error."""


@dataclass
@PayloadRegistry.register
class RegisterWorkflowsFromConfigRequest(RequestPayload):
    """Register workflows from configuration section.

    Use when: Loading workflows from configuration after library initialization,
    registering workflows from synced directories, batch workflow registration.

    Args:
        config_section: Configuration section path containing workflow paths to register

    Results: RegisterWorkflowsFromConfigResultSuccess (with count) | RegisterWorkflowsFromConfigResultFailure (registration error)
    """

    config_section: str


@dataclass
@PayloadRegistry.register
class RegisterWorkflowsFromConfigResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflows registered from configuration successfully.

    Args:
        succeeded_workflows: List of workflow names that were successfully registered
        failed_workflows: List of workflow names that failed to register
    """

    succeeded_workflows: list[str]
    failed_workflows: list[str]


@dataclass
@PayloadRegistry.register
class RegisterWorkflowsFromConfigResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow registration from configuration failed. Common causes: configuration not found, invalid paths, registration errors."""


@dataclass
@PayloadRegistry.register
class SaveWorkflowFileFromSerializedFlowRequest(RequestPayload):
    """Save a workflow file from serialized flow commands without registry overhead.

    Use when: Creating workflow files from user-supplied subsets of existing workflows,
    exporting partial workflows, creating standalone workflow files without registration.

    Args:
        serialized_flow_commands: The serialized commands representing the workflow structure
        file_name: Name for the workflow file (without .py extension)
        creation_date: Optional creation date for the workflow metadata (defaults to current time if not provided)
        image_path: Optional path to workflow image/thumbnail
        execution_flow_name: Optional flow name to use for execution code (defaults to file_name if not provided)
        branched_from: Optional branched from information to preserve workflow lineage
        workflow_shape: Optional workflow shape defining inputs and outputs for external callers
        file_path: Optional specific file path to use (defaults to workspace path if not provided)
        pickle_control_flow_result: Whether to pickle control flow results in generated execution code (defaults to False)

    Results: SaveWorkflowFileFromSerializedFlowResultSuccess (with file path) | SaveWorkflowFileFromSerializedFlowResultFailure (save error)
    """

    serialized_flow_commands: "SerializedFlowCommands"
    file_name: str
    file_path: str | None = None
    creation_date: datetime | None = None
    image_path: str | None = None
    execution_flow_name: str | None = None
    branched_from: str | None = None
    workflow_shape: WorkflowShape | None = None
    pickle_control_flow_result: bool = False


@dataclass
@PayloadRegistry.register
class SaveWorkflowFileFromSerializedFlowResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Workflow file saved successfully from serialized flow commands.

    Args:
        file_path: Path where the workflow file was written
        workflow_metadata: The metadata that was generated for the workflow
    """

    file_path: str
    workflow_metadata: WorkflowMetadata


@dataclass
@PayloadRegistry.register
class SaveWorkflowFileFromSerializedFlowResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Workflow file save failed. Common causes: file system error, permission denied, invalid serialized commands."""
