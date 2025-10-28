"""ProjectManager - Manages project templates and file save situations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.common.macro_parser import (
    MacroMatchFailure,
    MacroMatchFailureReason,
    MacroParseFailure,
    MacroParseFailureReason,
    MacroResolutionError,
    MacroResolutionFailureReason,
    MacroSyntaxError,
    ParsedMacro,
)
from griptape_nodes.common.project_templates import (
    DEFAULT_PROJECT_TEMPLATE,
    ProjectTemplate,
    ProjectValidationInfo,
    ProjectValidationStatus,
    load_project_template_from_yaml,
)
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete  # noqa: TC001
from griptape_nodes.retained_mode.events.os_events import ReadFileRequest, ReadFileResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultFailure,
    GetAllSituationsForProjectResultSuccess,
    GetCurrentProjectRequest,
    GetCurrentProjectResultSuccess,
    GetMacroForSituationRequest,
    GetMacroForSituationResultFailure,
    GetMacroForSituationResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetProjectTemplateRequest,
    GetProjectTemplateResultFailure,
    GetProjectTemplateResultSuccess,
    GetVariablesForMacroRequest,
    GetVariablesForMacroResultFailure,
    GetVariablesForMacroResultSuccess,
    LoadProjectTemplateRequest,
    LoadProjectTemplateResultFailure,
    LoadProjectTemplateResultSuccess,
    MatchPathAgainstMacroRequest,
    MatchPathAgainstMacroResultFailure,
    MatchPathAgainstMacroResultSuccess,
    PathResolutionFailureReason,
    SaveProjectTemplateRequest,
    SaveProjectTemplateResultFailure,
    SetCurrentProjectRequest,
    SetCurrentProjectResultSuccess,
    ValidateMacroSyntaxRequest,
    ValidateMacroSyntaxResultFailure,
    ValidateMacroSyntaxResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")

# Synthetic path key for the system default project template
SYSTEM_DEFAULTS_KEY = Path("<system-defaults>")


@dataclass(frozen=True)
class SituationMacroKey:
    """Key for caching parsed situation schema macros."""

    project_path: Path
    situation_name: str


@dataclass(frozen=True)
class DirectoryMacroKey:
    """Key for caching parsed directory schema macros."""

    project_path: Path
    directory_name: str


class ProjectManager:
    """Manages project templates, validation, and file path resolution.

    Responsibilities:
    - Load and cache project templates (system defaults + user customizations)
    - Track validation status for all load attempts (including MISSING files)
    - Parse and cache macro schemas for performance
    - Resolve file paths using situation templates and variable substitution
    - Manage current project selection
    - Handle project.yml file I/O via OSManager events

    State tracking uses two dicts:
    - registered_template_status: ALL load attempts (Path -> ProjectValidationInfo)
    - successful_templates: Only usable templates (Path -> ProjectTemplate)

    This allows UI to query validation status even when template failed to load.
    """

    def __init__(
        self,
        event_manager: EventManager | None = None,
        config_manager: ConfigManager | None = None,
        secrets_manager: SecretsManager | None = None,
    ) -> None:
        """Initialize the ProjectManager.

        Args:
            event_manager: The EventManager instance to use for event handling
            config_manager: ConfigManager instance for accessing configuration
            secrets_manager: SecretsManager instance for macro resolution
        """
        self.config_manager = config_manager
        self.secrets_manager = secrets_manager

        # Track validation status for ALL load attempts (including MISSING/UNUSABLE)
        self.registered_template_status: dict[Path, ProjectValidationInfo] = {}

        # Cache only successfully loaded templates (GOOD or FLAWED)
        self.successful_templates: dict[Path, ProjectTemplate] = {}

        # Cache parsed macros for performance (avoid re-parsing schemas)
        self.parsed_situation_schemas: dict[SituationMacroKey, ParsedMacro] = {}
        self.parsed_directory_schemas: dict[DirectoryMacroKey, ParsedMacro] = {}

        # Track which project.yml user has selected
        self.current_project_path: Path | None = None

        # Register event handlers
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                LoadProjectTemplateRequest, self.on_load_project_template_request
            )
            event_manager.assign_manager_to_request_type(
                GetProjectTemplateRequest, self.on_get_project_template_request
            )
            event_manager.assign_manager_to_request_type(
                GetMacroForSituationRequest, self.on_get_macro_for_situation_request
            )
            event_manager.assign_manager_to_request_type(GetPathForMacroRequest, self.on_get_path_for_macro_request)
            event_manager.assign_manager_to_request_type(SetCurrentProjectRequest, self.on_set_current_project_request)
            event_manager.assign_manager_to_request_type(GetCurrentProjectRequest, self.on_get_current_project_request)
            event_manager.assign_manager_to_request_type(
                SaveProjectTemplateRequest, self.on_save_project_template_request
            )
            event_manager.assign_manager_to_request_type(
                MatchPathAgainstMacroRequest, self.on_match_path_against_macro_request
            )
            event_manager.assign_manager_to_request_type(
                GetVariablesForMacroRequest, self.on_get_variables_for_macro_request
            )
            event_manager.assign_manager_to_request_type(
                ValidateMacroSyntaxRequest, self.on_validate_macro_syntax_request
            )
            event_manager.assign_manager_to_request_type(
                GetAllSituationsForProjectRequest, self.on_get_all_situations_for_project_request
            )

            # Register app initialization listener
            # NOTE: This is intentionally commented out to keep ProjectManager inert for code review.
            # Uncomment the following lines to enable ProjectManager during app initialization.
            # ruff: noqa: ERA001
            # event_manager.add_listener_to_app_event(
            #     AppInitializationComplete,
            #     self.on_app_initialization_complete,
            # )

    # Event handler methods (public)

    def on_load_project_template_request(self, request: LoadProjectTemplateRequest) -> ResultPayload:
        """Load user's project.yml and merge with system defaults.

        Flow:
        1. Issue ReadFileRequest to OSManager (for proper Windows long path handling)
        2. Parse YAML and load partial template (overlay) using load_partial_project_template()
        3. Merge with system defaults using ProjectTemplate.merge()
        4. Cache validation in registered_template_status
        5. If usable, cache template in successful_templates
        6. Return LoadProjectTemplateResultSuccess or LoadProjectTemplateResultFailure
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        logger.debug("Loading project template: %s", request.project_path)

        read_request = ReadFileRequest(
            file_path=str(request.project_path),
            encoding="utf-8",
            workspace_only=False,
        )
        read_result = GriptapeNodes.handle_request(read_request)

        if read_result.failed():
            validation = ProjectValidationInfo(status=ProjectValidationStatus.MISSING)
            self.registered_template_status[request.project_path] = validation

            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"File not found: {request.project_path}",
            )

        if not isinstance(read_result, ReadFileResultSuccess):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self.registered_template_status[request.project_path] = validation

            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details="Unexpected result type from ReadFileRequest",
            )

        yaml_text = read_result.content
        if not isinstance(yaml_text, str):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self.registered_template_status[request.project_path] = validation

            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details="Template must be text, got binary content",
            )

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        template = load_project_template_from_yaml(yaml_text, validation)

        if template is None:
            self.registered_template_status[request.project_path] = validation
            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details="Failed to parse YAML template",
            )

        if not validation.is_usable():
            self.registered_template_status[request.project_path] = validation
            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"Template not usable (status: {validation.status})",
            )

        logger.debug("Template loaded successfully (status: %s)", validation.status)

        self.registered_template_status[request.project_path] = validation
        self.successful_templates[request.project_path] = template

        return LoadProjectTemplateResultSuccess(
            project_path=request.project_path,
            template=template,
            validation=validation,
            result_details=f"Template loaded successfully with status: {validation.status}",
        )

    def on_get_project_template_request(self, request: GetProjectTemplateRequest) -> ResultPayload:
        """Get cached template for a workspace path."""
        if request.project_path not in self.registered_template_status:
            return GetProjectTemplateResultFailure(
                result_details=f"Template not loaded yet: {request.project_path}",
            )

        validation = self.registered_template_status[request.project_path]
        template = self.successful_templates.get(request.project_path)

        if template is None:
            return GetProjectTemplateResultFailure(
                result_details=f"Template not usable (status: {validation.status})",
            )

        return GetProjectTemplateResultSuccess(
            template=template,
            validation=validation,
            result_details="Project template retrieved from cache",
        )

    def on_get_macro_for_situation_request(self, request: GetMacroForSituationRequest) -> ResultPayload:
        """Get the macro schema for a specific situation.

        Flow:
        1. Get template from successful_templates
        2. Get situation from template
        3. Return situation's macro schema
        """
        logger.debug("Getting macro for situation: %s in project: %s", request.situation_name, request.project_path)

        template = self.successful_templates.get(request.project_path)
        if template is None:
            return GetMacroForSituationResultFailure(
                result_details=f"Project template not loaded: {request.project_path}",
            )

        situation = template.situations.get(request.situation_name)
        if situation is None:
            return GetMacroForSituationResultFailure(
                result_details=f"Situation not found: {request.situation_name}",
            )

        return GetMacroForSituationResultSuccess(
            macro_schema=situation.schema,
            result_details=f"Retrieved schema for situation: {request.situation_name}",
        )

    def on_get_path_for_macro_request(self, request: GetPathForMacroRequest) -> ResultPayload:  # noqa: C901, PLR0911
        """Resolve ANY macro schema with variables to final Path.

        Flow:
        1. Parse macro schema with ParsedMacro
        2. Get variables from ParsedMacro.get_variables()
        3. For each variable:
           - If in directories dict → resolve directory, add to resolution bag
           - Else if in user_supplied_vars → use user value
           - If in BOTH → ERROR: DIRECTORY_OVERRIDE_ATTEMPTED
           - Else → collect as missing
        4. If any missing → ERROR: MISSING_REQUIRED_VARIABLES
        5. Resolve macro with complete variable bag
        6. Return resolved Path
        """
        logger.debug("Resolving macro: %s in project: %s", request.macro_schema, request.project_path)

        try:
            parsed_macro = ParsedMacro(request.macro_schema)
        except MacroSyntaxError as e:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                error_details=str(e),
                result_details=f"Invalid macro syntax: {e}",
            )

        template = self.successful_templates.get(request.project_path)
        if template is None:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                error_details="Project template not loaded",
                result_details=f"Project template not loaded: {request.project_path}",
            )

        variable_infos = parsed_macro.get_variables()
        directory_names = set(template.directories.keys())
        user_provided_names = set(request.variables.keys())

        conflicting = directory_names & user_provided_names
        if conflicting:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED,
                conflicting_variables=sorted(conflicting),
                result_details=f"Variables conflict with directory names: {', '.join(sorted(conflicting))}",
            )

        resolution_bag: dict[str, str | int] = {}

        for var_info in variable_infos:
            var_name = var_info.name

            if var_name in directory_names:
                directory_def = template.directories[var_name]
                resolution_bag[var_name] = directory_def.path_schema
            elif var_name in user_provided_names:
                resolution_bag[var_name] = request.variables[var_name]

        required_vars = {v.name for v in variable_infos if v.is_required}
        provided_vars = set(resolution_bag.keys())
        missing = required_vars - provided_vars

        if missing:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                missing_variables=sorted(missing),
                result_details=f"Missing required variables: {', '.join(sorted(missing))}",
            )

        if self.secrets_manager is None:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                error_details="SecretsManager not available",
                result_details="SecretsManager not available",
            )

        try:
            resolved_string = parsed_macro.resolve(resolution_bag, self.secrets_manager)
        except MacroResolutionError as e:
            if e.failure_reason == MacroResolutionFailureReason.MISSING_REQUIRED_VARIABLES:
                path_failure_reason = PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES
            else:
                path_failure_reason = PathResolutionFailureReason.MACRO_RESOLUTION_ERROR

            return GetPathForMacroResultFailure(
                failure_reason=path_failure_reason,
                missing_variables=e.missing_variables,
                error_details=str(e),
                result_details=f"Macro resolution failed: {e}",
            )

        resolved_path = Path(resolved_string)

        return GetPathForMacroResultSuccess(
            resolved_path=resolved_path,
            result_details=f"Resolved to: {resolved_path}",
        )

    def on_set_current_project_request(self, request: SetCurrentProjectRequest) -> ResultPayload:
        """Set which project.yml user has selected."""
        self.current_project_path = request.project_path

        if request.project_path is None:
            logger.info("Current project set to: No Project")
        else:
            logger.info("Current project set to: %s", request.project_path)

        return SetCurrentProjectResultSuccess(
            result_details="Current project set successfully",
        )

    def on_get_current_project_request(self, _request: GetCurrentProjectRequest) -> ResultPayload:
        """Get currently selected project path."""
        return GetCurrentProjectResultSuccess(
            project_path=self.current_project_path,
            result_details="Current project retrieved successfully",
        )

    def on_save_project_template_request(self, request: SaveProjectTemplateRequest) -> ResultPayload:
        """Save user customizations to project.yml.

        Flow:
        1. Convert template_data to YAML format
        2. Issue WriteFileRequest to OSManager
        3. Handle write result
        4. Invalidate cache (force reload on next access)

        TODO: Implement saving logic when template system merges
        """
        logger.debug("Saving project template: %s", request.project_path)

        return SaveProjectTemplateResultFailure(
            project_path=request.project_path,
            result_details="Template saving not yet implemented (stub)",
        )

    def on_match_path_against_macro_request(self, request: MatchPathAgainstMacroRequest) -> ResultPayload:
        """Check if a path matches a macro schema and extract variables.

        Flow:
        1. Parse macro schema into ParsedMacro
        2. Call ParsedMacro.extract_variables() with path and known variables
        3. If match succeeds, return extracted variables
        4. If match fails, return MacroMatchFailure with details
        """
        logger.debug("Matching path against macro: %s", request.macro_schema)

        if self.secrets_manager is None:
            return MatchPathAgainstMacroResultFailure(
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.INVALID_MACRO_SYNTAX,
                    expected_pattern=request.macro_schema,
                    known_variables_used=request.known_variables,
                    error_details="SecretsManager not available",
                ),
                result_details="SecretsManager not available for macro matching",
            )

        try:
            parsed_macro = ParsedMacro(request.macro_schema)
        except MacroSyntaxError as err:
            return MatchPathAgainstMacroResultFailure(
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.INVALID_MACRO_SYNTAX,
                    expected_pattern=request.macro_schema,
                    known_variables_used=request.known_variables,
                    error_details=str(err),
                ),
                result_details=f"Invalid macro syntax: {err}",
            )

        extracted = parsed_macro.extract_variables(
            request.file_path,
            request.known_variables,
            self.secrets_manager,
        )

        if extracted is None:
            return MatchPathAgainstMacroResultFailure(
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.STATIC_TEXT_MISMATCH,
                    expected_pattern=request.macro_schema,
                    known_variables_used=request.known_variables,
                    error_details=f"Path '{request.file_path}' does not match macro pattern",
                ),
                result_details="Path does not match macro pattern",
            )

        return MatchPathAgainstMacroResultSuccess(
            extracted_variables=extracted,
            result_details="Successfully matched path against macro",
        )

    def on_get_variables_for_macro_request(self, request: GetVariablesForMacroRequest) -> ResultPayload:
        """Get list of all variables in a macro schema.

        Flow:
        1. Parse macro schema into ParsedMacro
        2. Call ParsedMacro.get_variables() to extract variable metadata
        3. Return list of VariableInfo
        """
        logger.debug("Getting variables for macro: %s", request.macro_schema)

        try:
            parsed_macro = ParsedMacro(request.macro_schema)
        except MacroSyntaxError as err:
            return GetVariablesForMacroResultFailure(
                parse_failure=MacroParseFailure(
                    failure_reason=err.failure_reason or MacroParseFailureReason.UNEXPECTED_SEGMENT_TYPE,
                    error_position=err.error_position,
                    error_details=str(err),
                ),
                result_details=f"Failed to parse macro: {err}",
            )

        variables = parsed_macro.get_variables()

        return GetVariablesForMacroResultSuccess(
            variables=variables,
            result_details=f"Found {len(variables)} variables in macro",
        )

    def on_validate_macro_syntax_request(self, request: ValidateMacroSyntaxRequest) -> ResultPayload:
        """Validate a macro schema string for syntax errors.

        Flow:
        1. Try to parse macro schema with ParsedMacro()
        2. If successful, return variables found and any warnings
        3. If syntax error, return MacroParseFailure with details
        """
        logger.debug("Validating macro syntax: %s", request.macro_schema)

        try:
            parsed_macro = ParsedMacro(request.macro_schema)
        except MacroSyntaxError as err:
            return ValidateMacroSyntaxResultFailure(
                parse_failure=MacroParseFailure(
                    failure_reason=err.failure_reason or MacroParseFailureReason.UNEXPECTED_SEGMENT_TYPE,
                    error_position=err.error_position,
                    error_details=str(err),
                ),
                partial_variables=[],
                result_details=f"Syntax validation failed: {err}",
            )

        variables = parsed_macro.get_variables()

        return ValidateMacroSyntaxResultSuccess(
            variables=variables,
            warnings=[],
            result_details=f"Macro syntax is valid with {len(variables)} variables",
        )

    async def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        """Load system default project template when app initializes.

        Called by EventManager after all libraries are loaded.
        """
        logger.debug("ProjectManager: Loading system default project template")

        self._load_system_defaults()

        # Set as current project (using synthetic key for system defaults)
        set_request = SetCurrentProjectRequest(project_path=SYSTEM_DEFAULTS_KEY)
        result = self.on_set_current_project_request(set_request)

        if result.failed():
            logger.error("Failed to set default project as current: %s", result.result_details)
        else:
            logger.debug("Successfully loaded default project template")

    def on_get_all_situations_for_project_request(self, request: GetAllSituationsForProjectRequest) -> ResultPayload:
        """Get all situation names and schemas from a project template."""
        logger.debug("Getting all situations for project: %s", request.project_path)

        template_info = self.registered_template_status.get(request.project_path)

        if template_info is None:
            self._load_system_defaults()
            template_info = self.registered_template_status.get(request.project_path)

        if template_info is None or template_info.status != ProjectValidationStatus.GOOD:
            return GetAllSituationsForProjectResultFailure(result_details="Project template not available or invalid")

        template = self.successful_templates[request.project_path]
        situations = {situation_name: situation.schema for situation_name, situation in template.situations.items()}

        return GetAllSituationsForProjectResultSuccess(
            situations=situations, result_details=f"Found {len(situations)} situations"
        )

    # Private helper methods

    def _load_system_defaults(self) -> None:
        """Load bundled system default template.

        System defaults are now defined in Python as DEFAULT_PROJECT_TEMPLATE.
        This is always valid by construction.
        """
        logger.debug("Loading system default template")

        # Create validation info to track that defaults were loaded
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        logger.debug("System defaults loaded successfully")

        self.registered_template_status[SYSTEM_DEFAULTS_KEY] = validation
        self.successful_templates[SYSTEM_DEFAULTS_KEY] = DEFAULT_PROJECT_TEMPLATE
