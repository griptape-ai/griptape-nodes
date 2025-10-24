"""Events for project template management."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from griptape_nodes.common.macro_parser import MacroMatchFailure, MacroParseFailure, VariableInfo
from griptape_nodes.common.project_templates import ProjectTemplate, ProjectValidationInfo
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

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
        project_path: Path to the loaded project.yml
        template: The merged ProjectTemplate (system defaults + user customizations)
        validation: Validation info with status and any problems encountered
    """

    project_path: Path
    template: ProjectTemplate
    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class LoadProjectTemplateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Project template loading failed.

    Args:
        project_path: Path to the project.yml that failed to load
        validation: Validation info with error details
    """

    project_path: Path
    validation: ProjectValidationInfo


@dataclass
@PayloadRegistry.register
class GetProjectTemplateRequest(RequestPayload):
    """Get cached project template for a workspace path.

    Use when: Querying current project configuration, checking validation status.

    Args:
        project_path: Path to the project.yml file

    Results: GetProjectTemplateResultSuccess | GetProjectTemplateResultFailure
    """

    project_path: Path


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
@PayloadRegistry.register
class GetMacroForSituationRequest(RequestPayload):
    """Get the macro schema for a specific situation.

    Use when: Need to know what variables a situation requires, or get schema for custom resolution.

    Args:
        project_path: Path to the project.yml to use
        situation_name: Name of the situation template (e.g., "save_node_output")

    Results: GetMacroForSituationResultSuccess | GetMacroForSituationResultFailure
    """

    project_path: Path
    situation_name: str


@dataclass
@PayloadRegistry.register
class GetMacroForSituationResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Situation macro retrieved successfully.

    Args:
        macro_schema: The macro template string (e.g., "{inputs}/{file_name}.{file_ext}")
    """

    macro_schema: str


@dataclass
@PayloadRegistry.register
class GetMacroForSituationResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Situation macro retrieval failed (situation not found or template not loaded)."""


@dataclass
@PayloadRegistry.register
class GetPathForMacroRequest(RequestPayload):
    """Resolve ANY macro schema with variables to produce final file path.

    Use when: Resolving paths, saving files. Works with any macro string, not tied to situations.

    Args:
        project_path: Path to the project.yml (used for directory resolution)
        macro_schema: The macro template string to resolve (e.g., "{inputs}/{file_name}.{file_ext}")
        variables: Variable values for macro substitution (e.g., {"file_name": "output", "file_ext": "png"})

    Results: GetPathForMacroResultSuccess | GetPathForMacroResultFailure
    """

    project_path: Path
    macro_schema: str
    variables: MacroVariables


@dataclass
@PayloadRegistry.register
class GetPathForMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Path resolved successfully from macro.

    Args:
        resolved_path: The final Path after macro substitution
    """

    resolved_path: Path


@dataclass
@PayloadRegistry.register
class GetPathForMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Path resolution failed.

    Args:
        failure_reason: Specific reason for failure
        missing_variables: List of required variable names that were not provided (for MISSING_REQUIRED_VARIABLES)
        conflicting_variables: List of variables that conflict with directory names (for DIRECTORY_OVERRIDE_ATTEMPTED)
        error_details: Additional error details from ParsedMacro (for MACRO_RESOLUTION_ERROR)
    """

    failure_reason: PathResolutionFailureReason
    missing_variables: list[str] | None = None
    conflicting_variables: list[str] | None = None
    error_details: str | None = None


@dataclass
@PayloadRegistry.register
class SetCurrentProjectRequest(RequestPayload):
    """Set which project.yml user has currently selected.

    Use when: User switches between projects, opens a new workspace.

    Args:
        project_path: Path to the project.yml to set as current (None to clear)

    Results: SetCurrentProjectResultSuccess
    """

    project_path: Path | None


@dataclass
@PayloadRegistry.register
class SetCurrentProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Current project set successfully."""


@dataclass
@PayloadRegistry.register
class GetCurrentProjectRequest(RequestPayload):
    """Get the currently selected project path.

    Use when: Need to know which project user is working with.

    Results: GetCurrentProjectResultSuccess
    """


@dataclass
@PayloadRegistry.register
class GetCurrentProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Current project retrieved.

    Args:
        project_path: The currently selected project path ("No Project" if None)
    """

    project_path: Path | None


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
    """Project template saved successfully.

    Args:
        project_path: Path where project.yml was saved
    """

    project_path: Path


@dataclass
@PayloadRegistry.register
class SaveProjectTemplateResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Project template save failed.

    Common causes:
    - Permission denied
    - Invalid path
    - Disk full
    """

    project_path: Path


@dataclass
@PayloadRegistry.register
class MatchPathAgainstMacroRequest(RequestPayload):
    """Check if a path matches a macro schema and extract variables.

    Use when: Validating paths, extracting info from file paths,
    identifying which schema produced a file.

    Args:
        project_path: Path to project.yml (for directory resolution)
        macro_schema: Macro template string
        file_path: Path to test
        known_variables: Variables we already know

    Results: MatchPathAgainstMacroResultSuccess | MatchPathAgainstMacroResultFailure
    """

    project_path: Path
    macro_schema: str
    file_path: str
    known_variables: MacroVariables


@dataclass
@PayloadRegistry.register
class MatchPathAgainstMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Path matched the macro schema."""

    extracted_variables: MacroVariables


@dataclass
@PayloadRegistry.register
class MatchPathAgainstMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Path did not match the macro schema."""

    match_failure: MacroMatchFailure


@dataclass
@PayloadRegistry.register
class GetVariablesForMacroRequest(RequestPayload):
    """Get list of all variables in a macro schema.

    Use when: Building UI forms, showing what variables a schema needs,
    validating before resolution.

    Args:
        macro_schema: Macro template string to inspect

    Results: GetVariablesForMacroResultSuccess | GetVariablesForMacroResultFailure
    """

    macro_schema: str


@dataclass
@PayloadRegistry.register
class GetVariablesForMacroResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Variables found in the macro schema."""

    variables: list[VariableInfo]


@dataclass
@PayloadRegistry.register
class GetVariablesForMacroResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failed to parse macro schema."""

    parse_failure: MacroParseFailure


@dataclass
@PayloadRegistry.register
class ValidateMacroSyntaxRequest(RequestPayload):
    """Validate a macro schema string for syntax errors.

    Use when: User editing schemas in UI, before saving templates,
    real-time validation.

    Args:
        macro_schema: Schema string to validate

    Results: ValidateMacroSyntaxResultSuccess | ValidateMacroSyntaxResultFailure
    """

    macro_schema: str


@dataclass
@PayloadRegistry.register
class ValidateMacroSyntaxResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Syntax is valid."""

    variables: list[VariableInfo]
    warnings: list[str]


@dataclass
@PayloadRegistry.register
class ValidateMacroSyntaxResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Syntax is invalid."""

    parse_failure: MacroParseFailure
    partial_variables: list[VariableInfo]


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectRequest(RequestPayload):
    """Get all situation names and schemas from a project template."""

    project_path: Path


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Success result containing all situations."""

    situations: dict[str, str]


@dataclass
@PayloadRegistry.register
class GetAllSituationsForProjectResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Failure result when cannot get situations."""
