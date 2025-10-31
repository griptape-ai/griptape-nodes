"""Events for project template management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.common.macro_parser import MacroMatchFailure, ParsedMacro, VariableInfo
    from griptape_nodes.common.project_templates import ProjectTemplate, ProjectValidationInfo, SituationTemplate
    from griptape_nodes.retained_mode.managers.project_manager import ProjectID, ProjectInfo

# Type alias for macro variable dictionaries (used by ParsedMacro)
MacroVariables = dict[str, str | int]


class PathResolutionFailureReason(StrEnum):
    """Reason why path resolution from macro failed."""

    MISSING_REQUIRED_VARIABLES = "MISSING_REQUIRED_VARIABLES"
    MACRO_RESOLUTION_ERROR = "MACRO_RESOLUTION_ERROR"
    DIRECTORY_OVERRIDE_ATTEMPTED = "DIRECTORY_OVERRIDE_ATTEMPTED"


@dataclass
@PayloadRegistry.register
class LoadProjectTemplateRequest(RequestPayload):
    """Load user's project.yml and merge with system defaults.

    Use when: User opens a workspace, user creates new project, user modifies project.yml.

    Args:
        project_path: Path to the project.yml file to load

    Results: LoadProjectTemplateResultSuccess | LoadProjectTemplateResultFailure
    """

    project_path: Path


@dataclass
@PayloadRegistry.register
class LoadProjectTemplateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Project template loaded successfully.

    Args:
        project_id: The identifier for the loaded project
        template: The merged ProjectTemplate (system defaults + user customizations)
        validation: Validation info with status and any problems encountered
    """

    project_id: ProjectID
    template: ProjectTemplate
    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class LoadProjectTemplateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Project template loading failed.

    Args:
        validation: Validation info with error details
    """

    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class GetProjectTemplateRequest(RequestPayload):
    """Get cached project template for a project ID.

    Use when: Querying current project configuration, checking validation status.

    Args:
        project_id: Identifier of the project

    Results: GetProjectTemplateResultSuccess | GetProjectTemplateResultFailure
    """

    project_id: ProjectID


@dataclass
@PayloadRegistry.register
class GetProjectTemplateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Project template retrieved from cache.

    Args:
        template: The successfully loaded ProjectTemplate
        validation: Validation info for the template
    """

    template: ProjectTemplate
    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class GetProjectTemplateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Project template retrieval failed (not loaded yet)."""


@dataclass
class ProjectTemplateInfo:
    """Information about a loaded or failed project template."""

    project_id: ProjectID
    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class ListProjectTemplatesRequest(RequestPayload):
    """List all project templates that have been loaded or attempted to load.

    Use when: Displaying available projects, checking which projects are loaded.

    Args:
        include_system_builtins: Whether to include system builtin templates like SYSTEM_DEFAULTS_KEY

    Results: ListProjectTemplatesResultSuccess
    """

    include_system_builtins: bool = False


@dataclass
@PayloadRegistry.register
class ListProjectTemplatesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """List of all project templates retrieved.

    Args:
        successfully_loaded: List of templates that loaded successfully
        failed_to_load: List of templates that failed to load with validation errors
    """

    successfully_loaded: list[ProjectTemplateInfo]
    failed_to_load: list[ProjectTemplateInfo]


@dataclass
@PayloadRegistry.register
class GetSituationRequest(RequestPayload):
    """Get the full situation template for a specific situation.

    Returns the complete SituationTemplate including macro and policy.

    Use when: Need situation macro and/or policy for file operations.
    Uses the current project for context.

    Args:
        situation_name: Name of the situation template (e.g., "save_node_output")

    Results: GetSituationResultSuccess | GetSituationResultFailure
    """

    situation_name: str


@dataclass
@PayloadRegistry.register
class GetSituationResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Situation template retrieved successfully.

    Args:
        situation: The complete situation template including macro and policy.
                  Access via situation.macro, situation.policy.create_dirs, etc.
    """

    situation: SituationTemplate


@dataclass
@PayloadRegistry.register
class GetSituationResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Situation template retrieval failed (situation not found or template not loaded)."""


@dataclass
@PayloadRegistry.register
class GetPathForMacroRequest(RequestPayload):
    """Resolve ANY macro schema with variables to produce final file path.

    Use when: Resolving paths, saving files. Works with any macro string, not tied to situations.

    Uses the current project for context. Caller must parse the macro string
    into a ParsedMacro before creating this request.

    Args:
        parsed_macro: The parsed macro to resolve
        variables: Variable values for macro substitution (e.g., {"file_name": "output", "file_ext": "png"})

    Results: GetPathForMacroResultSuccess | GetPathForMacroResultFailure
    """

    parsed_macro: ParsedMacro
    variables: MacroVariables


@dataclass
@PayloadRegistry.register
class GetPathForMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Path resolved successfully from macro.

    Args:
        resolved_path: The relative project path after macro substitution (e.g., "outputs/file.png")
        absolute_path: The absolute filesystem path (e.g., "/workspace/outputs/file.png")
    """

    resolved_path: Path
    absolute_path: Path


@dataclass
@PayloadRegistry.register
class GetPathForMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Path resolution failed.

    Args:
        failure_reason: Specific reason for failure
        missing_variables: List of required variable names that were not provided (for MISSING_REQUIRED_VARIABLES)
        conflicting_variables: List of variables that conflict with directory names (for DIRECTORY_OVERRIDE_ATTEMPTED)
    """

    failure_reason: PathResolutionFailureReason
    missing_variables: set[str] | None = None
    conflicting_variables: set[str] | None = None


@dataclass
@PayloadRegistry.register
class SetCurrentProjectRequest(RequestPayload):
    """Set which project user has currently selected.

    Use when: User switches between projects, opens a new workspace.

    Args:
        project_id: Identifier of the project to set as current (None to clear)

    Results: SetCurrentProjectResultSuccess
    """

    project_id: ProjectID | None


@dataclass
@PayloadRegistry.register
class SetCurrentProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Current project set successfully."""


@dataclass
@PayloadRegistry.register
class GetCurrentProjectRequest(RequestPayload):
    """Get the currently selected project path.

    Use when: Need to know which project user is working with.

    Results: GetCurrentProjectResultSuccess | GetCurrentProjectResultFailure
    """


@dataclass
@PayloadRegistry.register
class GetCurrentProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Current project retrieved.

    Args:
        project_info: Complete information about the current project
    """

    project_info: ProjectInfo


@dataclass
@PayloadRegistry.register
class GetCurrentProjectResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """No current project is set."""


@dataclass
@PayloadRegistry.register
class SaveProjectTemplateRequest(RequestPayload):
    """Save user customizations to project.yml file.

    Use when: User modifies project configuration, exports template.

    Args:
        project_path: Path where project.yml should be saved
        template_data: Dict representation of the template to save

    Results: SaveProjectTemplateResultSuccess | SaveProjectTemplateResultFailure
    """

    project_path: Path
    template_data: dict[str, Any]


@dataclass
@PayloadRegistry.register
class SaveProjectTemplateResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Project template saved successfully."""


@dataclass
@PayloadRegistry.register
class SaveProjectTemplateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Project template save failed.

    Common causes:
    - Permission denied
    - Invalid path
    - Disk full
    """


@dataclass
@PayloadRegistry.register
class AttemptMatchPathAgainstMacroRequest(RequestPayload):
    """Attempt to match a path against a macro schema and extract variables.

    Use when: Validating paths, extracting info from file paths,
    identifying which schema produced a file.

    Uses the current project for context. Caller must parse the macro string
    into a ParsedMacro before creating this request.

    Pattern non-matches are returned as success with match_failure populated.
    Only true system errors (missing SecretsManager, etc.) return failure.

    Args:
        parsed_macro: Parsed macro template to match against
        file_path: Path string to test
        known_variables: Variables we already know

    Results: AttemptMatchPathAgainstMacroResultSuccess | AttemptMatchPathAgainstMacroResultFailure
    """

    parsed_macro: ParsedMacro
    file_path: str
    known_variables: MacroVariables


@dataclass
@PayloadRegistry.register
class AttemptMatchPathAgainstMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Attempt completed (match succeeded or pattern didn't match).

    Check match_failure to determine outcome:
    - match_failure is None: Pattern matched, extracted_variables contains results
    - match_failure is not None: Pattern didn't match (normal case, not an error)
    """

    extracted_variables: MacroVariables | None
    match_failure: MacroMatchFailure | None


@dataclass
@PayloadRegistry.register
class AttemptMatchPathAgainstMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """System error occurred (missing SecretsManager, invalid configuration, etc.)."""


@dataclass
@PayloadRegistry.register
class GetStateForMacroRequest(RequestPayload):
    """Analyze a macro and return comprehensive state information.

    Use when: Building UI forms, real-time validation, checking if resolution
    would succeed before actually resolving.

    Uses the current project for context. Caller must parse the macro string
    into a ParsedMacro before creating this request.

    Args:
        parsed_macro: The parsed macro to analyze
        variables: Currently provided variable values

    Results: GetStateForMacroResultSuccess | GetStateForMacroResultFailure
    """

    parsed_macro: ParsedMacro
    variables: MacroVariables


@dataclass
@PayloadRegistry.register
class GetStateForMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Macro state analysis completed successfully.

    Args:
        all_variables: All variables found in the macro
        satisfied_variables: Variables that have values (from user, directories, or builtins)
        missing_required_variables: Required variables that are missing values
        conflicting_variables: Variables that conflict (e.g., user overriding builtin with different value)
        can_resolve: Whether the macro can be fully resolved (no missing required vars, no conflicts)
    """

    all_variables: set[VariableInfo]
    satisfied_variables: set[str]
    missing_required_variables: set[str]
    conflicting_variables: set[str]
    can_resolve: bool


@dataclass
@PayloadRegistry.register
class GetStateForMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Macro state analysis failed.

    Failure occurs when:
    - No current project is set
    - Current project template is not loaded
    - A builtin variable cannot be resolved (RuntimeError or NotImplementedError)
    """


@dataclass
@PayloadRegistry.register
class AttemptMapAbsolutePathToProjectRequest(RequestPayload):
    """Find out if an absolute path exists anywhere within a Project directory.

    Use when: User selects or types an absolute path via FilePicker and you need to know:
      1. Is this path inside any project directory?
      2. If yes, what's the macro form (e.g., {outputs}/file.png)?

    This enables automatic conversion of absolute paths to portable macro form for workflow portability.

    Uses longest prefix matching to find the most specific directory match.
    Returns Success with mapped_path if inside project, or Success with None if outside.
    Returns Failure if operation cannot be performed (no project loaded, secrets unavailable).

    Args:
        absolute_path: The absolute filesystem path to check

    Results: AttemptMapAbsolutePathToProjectResultSuccess | AttemptMapAbsolutePathToProjectResultFailure

    Examples:
        Path inside project directory:
            Request: absolute_path = /Users/james/project/outputs/renders/image.png
            Result: mapped_path = "{outputs}/renders/image.png"

        Path outside project:
            Request: absolute_path = /Users/james/Downloads/image.png
            Result: mapped_path = None

        Path at directory root:
            Request: absolute_path = /Users/james/project/outputs
            Result: mapped_path = "{outputs}"
    """

    absolute_path: Path


@dataclass
@PayloadRegistry.register
class AttemptMapAbsolutePathToProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Path check completed successfully.

    Success means the check was performed (not necessarily that a match was found).
    - mapped_path is NOT None: Path is inside a project directory (macro form returned)
    - mapped_path is None: Path is outside all project directories (valid answer)

    Args:
        mapped_path: The macro form if path is inside a project directory (e.g., "{outputs}/file.png"),
                    or None if path is outside all project directories

    Examples:
        Path inside project:
            mapped_path = "{outputs}/renders/image.png"
            result_details = "Successfully mapped absolute path to '{outputs}/renders/image.png'"

        Path outside project:
            mapped_path = None
            result_details = "Attempted to map absolute path '/Users/james/Downloads/image.png'. Path is outside all project directories"
    """

    mapped_path: str | None


@dataclass
@PayloadRegistry.register
class AttemptMapAbsolutePathToProjectResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Path mapping attempt failed.

    Returned when the operation cannot be performed (no current project, secrets manager unavailable).
    This is distinct from "path is outside project" which returns Success with None values.

    Examples:
        No current project:
            result_details = "Attempted to map absolute path. Failed because no current project is set"

        Secrets manager unavailable:
            result_details = "Attempted to map absolute path. Failed because SecretsManager not available"
    """


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectRequest(RequestPayload):
    """Get all situation names and schemas from current project template."""


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Success result containing all situations."""

    situations: dict[str, str]


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failure result when cannot get situations."""
