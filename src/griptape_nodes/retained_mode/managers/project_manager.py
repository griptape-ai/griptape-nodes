"""ProjectManager - Manages project templates and file save situations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.common.macro_parser import (
    MacroMatchFailure,
    MacroMatchFailureReason,
    MacroResolutionError,
    MacroResolutionFailureReason,
    ParsedMacro,
)
from griptape_nodes.common.project_templates import (
    DEFAULT_PROJECT_TEMPLATE,
    ProjectTemplate,
    ProjectValidationInfo,
    ProjectValidationStatus,
    load_project_template_from_yaml,
)
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.os_events import ReadFileRequest, ReadFileResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultFailure,
    GetAllSituationsForProjectResultSuccess,
    GetCurrentProjectRequest,
    GetCurrentProjectResultFailure,
    GetCurrentProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetProjectTemplateRequest,
    GetProjectTemplateResultFailure,
    GetProjectTemplateResultSuccess,
    GetSituationRequest,
    GetSituationResultFailure,
    GetSituationResultSuccess,
    GetStateForMacroRequest,
    GetStateForMacroResultFailure,
    GetStateForMacroResultSuccess,
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
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")

# Synthetic path key for the system default project template
SYSTEM_DEFAULTS_KEY = Path("<system-defaults>")

# Builtin variable name constants
BUILTIN_PROJECT_DIR = "project_dir"
BUILTIN_PROJECT_NAME = "project_name"
BUILTIN_WORKSPACE_DIR = "workspace_dir"
BUILTIN_WORKFLOW_NAME = "workflow_name"
BUILTIN_WORKFLOW_DIR = "workflow_dir"

# Builtin variables available in all macros (read-only)
BUILTIN_VARIABLES = frozenset(
    [
        BUILTIN_PROJECT_DIR,
        BUILTIN_PROJECT_NAME,
        BUILTIN_WORKFLOW_NAME,
        BUILTIN_WORKFLOW_DIR,
        BUILTIN_WORKSPACE_DIR,
    ]
)


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
            event_manager.assign_manager_to_request_type(GetSituationRequest, self.on_get_situation_request)
            event_manager.assign_manager_to_request_type(GetPathForMacroRequest, self.on_get_path_for_macro_request)
            event_manager.assign_manager_to_request_type(SetCurrentProjectRequest, self.on_set_current_project_request)
            event_manager.assign_manager_to_request_type(GetCurrentProjectRequest, self.on_get_current_project_request)
            event_manager.assign_manager_to_request_type(
                SaveProjectTemplateRequest, self.on_save_project_template_request
            )
            event_manager.assign_manager_to_request_type(
                MatchPathAgainstMacroRequest, self.on_match_path_against_macro_request
            )
            event_manager.assign_manager_to_request_type(GetStateForMacroRequest, self.on_get_state_for_macro_request)
            event_manager.assign_manager_to_request_type(
                GetAllSituationsForProjectRequest, self.on_get_all_situations_for_project_request
            )

            # Register app initialization listener
            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )

    def on_load_project_template_request(
        self, request: LoadProjectTemplateRequest
    ) -> LoadProjectTemplateResultSuccess | LoadProjectTemplateResultFailure:
        """Load user's project.yml and merge with system defaults.

        Flow:
        1. Issue ReadFileRequest to OSManager (for proper Windows long path handling)
        2. Parse YAML and load partial template (overlay) using load_partial_project_template()
        3. Merge with system defaults using ProjectTemplate.merge()
        4. Cache validation in registered_template_status
        5. If usable, cache template in successful_templates
        6. Return LoadProjectTemplateResultSuccess or LoadProjectTemplateResultFailure
        """
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
                result_details=f"Attempted to load project template from '{request.project_path}'. Failed because file not found",
            )

        if not isinstance(read_result, ReadFileResultSuccess):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self.registered_template_status[request.project_path] = validation

            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"Attempted to load project template from '{request.project_path}'. Failed because file read returned unexpected result type",
            )

        yaml_text = read_result.content
        if not isinstance(yaml_text, str):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self.registered_template_status[request.project_path] = validation

            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"Attempted to load project template from '{request.project_path}'. Failed because template must be text, got binary content",
            )

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        template = load_project_template_from_yaml(yaml_text, validation)

        if template is None:
            self.registered_template_status[request.project_path] = validation
            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"Attempted to load project template from '{request.project_path}'. Failed because YAML could not be parsed",
            )

        if not validation.is_usable():
            self.registered_template_status[request.project_path] = validation
            return LoadProjectTemplateResultFailure(
                project_path=request.project_path,
                validation=validation,
                result_details=f"Attempted to load project template from '{request.project_path}'. Failed because template is not usable (status: {validation.status})",
            )

        self.registered_template_status[request.project_path] = validation
        self.successful_templates[request.project_path] = template

        # Populate macro caches for performance
        self._populate_macro_caches_for_template(request.project_path, template)

        return LoadProjectTemplateResultSuccess(
            project_path=request.project_path,
            template=template,
            validation=validation,
            result_details=f"Template loaded successfully with status: {validation.status}",
        )

    def on_get_project_template_request(
        self, request: GetProjectTemplateRequest
    ) -> GetProjectTemplateResultSuccess | GetProjectTemplateResultFailure:
        """Get cached template for a workspace path."""
        if request.project_path not in self.registered_template_status:
            return GetProjectTemplateResultFailure(
                result_details=f"Attempted to get project template for '{request.project_path}'. Failed because template not loaded yet",
            )

        validation = self.registered_template_status[request.project_path]
        template = self.successful_templates.get(request.project_path)

        if template is None:
            return GetProjectTemplateResultFailure(
                result_details=f"Attempted to get project template for '{request.project_path}'. Failed because template not usable (status: {validation.status})",
            )

        return GetProjectTemplateResultSuccess(
            template=template,
            validation=validation,
            result_details=f"Successfully retrieved project template for '{request.project_path}'. Status: {validation.status}",
        )

    def on_get_situation_request(
        self, request: GetSituationRequest
    ) -> GetSituationResultSuccess | GetSituationResultFailure:
        """Get the complete situation template for a specific situation.

        Returns the full SituationTemplate including macro and policy.

        Flow:
        1. Get template from successful_templates
        2. Get situation from template
        3. Return complete SituationTemplate
        """
        template = self.successful_templates.get(request.project_path)
        if template is None:
            return GetSituationResultFailure(
                result_details=f"Attempted to get situation '{request.situation_name}' in project '{request.project_path}'. Failed because project template not loaded",
            )

        situation = template.situations.get(request.situation_name)
        if situation is None:
            return GetSituationResultFailure(
                result_details=f"Attempted to get situation '{request.situation_name}' in project '{request.project_path}'. Failed because situation not found",
            )

        return GetSituationResultSuccess(
            situation=situation,
            result_details=f"Successfully retrieved situation '{request.situation_name}'. Macro: {situation.macro}, Policy: create_dirs={situation.policy.create_dirs}, on_collision={situation.policy.on_collision}",
        )

    def on_get_path_for_macro_request(  # noqa: C901, PLR0911, PLR0912
        self, request: GetPathForMacroRequest
    ) -> GetPathForMacroResultSuccess | GetPathForMacroResultFailure:
        """Resolve ANY macro schema with variables to final Path.

        Flow:
        1. Get current project
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
        current_project_request = GetCurrentProjectRequest()
        current_project_result = self.on_get_current_project_request(current_project_request)

        if not isinstance(current_project_result, GetCurrentProjectResultSuccess):
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                result_details="Attempted to resolve macro path. Failed because no current project is set",
            )

        project_path = current_project_result.project_path

        template = self.successful_templates.get(project_path)
        if template is None:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                result_details=f"Attempted to resolve macro path. Failed because project template is not loaded for '{project_path}'",
            )

        variable_infos = request.parsed_macro.get_variables()
        directory_names = set(template.directories.keys())
        user_provided_names = set(request.variables.keys())

        # Check for directory/user variable name conflicts
        conflicting = directory_names & user_provided_names
        if conflicting:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED,
                conflicting_variables=conflicting,
                result_details=f"Attempted to resolve macro path. Failed because variables conflict with directory names: {', '.join(sorted(conflicting))}",
            )

        resolution_bag: dict[str, str | int] = {}
        disallowed_overrides: set[str] = set()

        for var_info in variable_infos:
            var_name = var_info.name

            if var_name in directory_names:
                directory_def = template.directories[var_name]
                resolution_bag[var_name] = directory_def.path_macro
            elif var_name in user_provided_names:
                resolution_bag[var_name] = request.variables[var_name]

            if var_name in BUILTIN_VARIABLES:
                try:
                    builtin_value = self._get_builtin_variable_value(var_name, project_path)
                except (RuntimeError, NotImplementedError) as e:
                    return GetPathForMacroResultFailure(
                        failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                        result_details=f"Attempted to resolve macro path. Failed because builtin variable '{var_name}' cannot be resolved: {e}",
                    )
                # Confirm no monkey business with trying to override builtin values
                existing = resolution_bag.get(var_name)
                if existing is not None:
                    if str(existing) != builtin_value:
                        disallowed_overrides.add(var_name)
                else:
                    resolution_bag[var_name] = builtin_value

        # Check if user tried to override builtins with different values
        if disallowed_overrides:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED,
                conflicting_variables=disallowed_overrides,
                result_details=f"Attempted to resolve macro path. Failed because cannot override builtin variables: {', '.join(sorted(disallowed_overrides))}",
            )

        required_vars = {v.name for v in variable_infos if v.is_required}
        provided_vars = set(resolution_bag.keys())
        missing = required_vars - provided_vars

        if missing:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                missing_variables=missing,
                result_details=f"Attempted to resolve macro path. Failed because missing required variables: {', '.join(sorted(missing))}",
            )

        if self.secrets_manager is None:
            return GetPathForMacroResultFailure(
                failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                result_details="Attempted to resolve macro path. Failed because SecretsManager is not available",
            )

        try:
            resolved_string = request.parsed_macro.resolve(resolution_bag, self.secrets_manager)
        except MacroResolutionError as e:
            if e.failure_reason == MacroResolutionFailureReason.MISSING_REQUIRED_VARIABLES:
                path_failure_reason = PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES
            else:
                path_failure_reason = PathResolutionFailureReason.MACRO_RESOLUTION_ERROR

            return GetPathForMacroResultFailure(
                failure_reason=path_failure_reason,
                missing_variables=e.missing_variables,
                result_details=f"Attempted to resolve macro path. Failed because macro resolution error: {e}",
            )

        resolved_path = Path(resolved_string)

        return GetPathForMacroResultSuccess(
            resolved_path=resolved_path,
            result_details=f"Successfully resolved macro path. Result: {resolved_path}",
        )

    def on_set_current_project_request(self, request: SetCurrentProjectRequest) -> SetCurrentProjectResultSuccess:
        """Set which project.yml user has selected."""
        self.current_project_path = request.project_path

        if request.project_path is None:
            return SetCurrentProjectResultSuccess(
                result_details="Successfully set current project. No project selected",
            )

        return SetCurrentProjectResultSuccess(
            result_details=f"Successfully set current project. Path: {request.project_path}",
        )

    def on_get_current_project_request(
        self, _request: GetCurrentProjectRequest
    ) -> GetCurrentProjectResultSuccess | GetCurrentProjectResultFailure:
        """Get currently selected project path."""
        if self.current_project_path is None:
            return GetCurrentProjectResultFailure(
                result_details="Attempted to get current project. Failed because no project is currently set"
            )

        return GetCurrentProjectResultSuccess(
            project_path=self.current_project_path,
            result_details=f"Successfully retrieved current project. Path: {self.current_project_path}",
        )

    def on_save_project_template_request(self, request: SaveProjectTemplateRequest) -> SaveProjectTemplateResultFailure:
        """Save user customizations to project.yml.

        Flow:
        1. Convert template_data to YAML format
        2. Issue WriteFileRequest to OSManager
        3. Handle write result
        4. Invalidate cache (force reload on next access)

        TODO: Implement saving logic when template system merges
        """
        return SaveProjectTemplateResultFailure(
            project_path=request.project_path,
            result_details=f"Attempted to save project template to '{request.project_path}'. Failed because template saving not yet implemented",
        )

    def on_match_path_against_macro_request(
        self, request: MatchPathAgainstMacroRequest
    ) -> MatchPathAgainstMacroResultSuccess | MatchPathAgainstMacroResultFailure:
        """Check if a path matches a macro schema and extract variables.

        Flow:
        1. Check secrets manager is available
        2. Call ParsedMacro.extract_variables() with path and known variables
        3. If match succeeds, return extracted variables
        4. If match fails, return MacroMatchFailure with details
        """
        if self.secrets_manager is None:
            return MatchPathAgainstMacroResultFailure(
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.INVALID_MACRO_SYNTAX,
                    expected_pattern=request.parsed_macro.template,
                    known_variables_used=request.known_variables,
                    error_details="SecretsManager not available",
                ),
                result_details=f"Attempted to match path '{request.file_path}' against macro '{request.parsed_macro.template}'. Failed because SecretsManager not available",
            )

        extracted = request.parsed_macro.extract_variables(
            request.file_path,
            request.known_variables,
            self.secrets_manager,
        )

        if extracted is None:
            return MatchPathAgainstMacroResultFailure(
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.STATIC_TEXT_MISMATCH,
                    expected_pattern=request.parsed_macro.template,
                    known_variables_used=request.known_variables,
                    error_details=f"Path '{request.file_path}' does not match macro pattern",
                ),
                result_details=f"Attempted to match path '{request.file_path}' against macro '{request.parsed_macro.template}'. Failed because path does not match pattern",
            )

        return MatchPathAgainstMacroResultSuccess(
            extracted_variables=extracted,
            result_details=f"Successfully matched path '{request.file_path}' against macro '{request.parsed_macro.template}'. Extracted {len(extracted)} variables",
        )

    def absolute_path_to_macro_path(self, absolute_path: Path, project_path: Path) -> str | None:  # noqa: C901
        """Convert an absolute path to macro form using longest prefix matching.

        Resolves all project directories at runtime (to support env vars and macros),
        then checks if the absolute path is within any of them.
        Uses longest prefix matching to find the best match.

        Args:
            absolute_path: Absolute path to convert (e.g., /Users/james/project/outputs/file.png)
            project_path: Path to the project.yml file

        Returns:
            Macro-ified path (e.g., {outputs}/file.png) if path is inside a project directory,
            None if path is outside all project directories

        Raises:
            RuntimeError: If secrets manager is not available or directory resolution fails

        Examples:
            /Users/james/project/outputs/renders/file.png → {outputs}/renders/file.png
            /Users/james/project/outputs/inputs/file.png → {outputs}/inputs/file.png (NOT {outputs}/{inputs}/...)
            /Users/james/Downloads/file.png → None (outside project)
        """
        template = self.successful_templates.get(project_path)
        if template is None:
            return None

        if self.secrets_manager is None:
            msg = "SecretsManager not available - cannot resolve directory macros"
            raise RuntimeError(msg)

        # Build builtin variables dict for directory resolution
        builtin_vars: dict[str, str | int] = {}
        for var_name in BUILTIN_VARIABLES:
            builtin_vars[var_name] = self._get_builtin_variable_value(var_name, project_path)

        # Find all matching directories (where absolute_path is inside the directory)
        class DirectoryMatch(NamedTuple):
            directory_name: str
            resolved_path: Path
            prefix_length: int

        matches: list[DirectoryMatch] = []

        for directory_name, directory_def in template.directories.items():
            # Resolve directory macro at runtime
            parsed_macro = self._get_parsed_directory_macro(project_path, directory_name, directory_def.path_macro)

            try:
                resolved_path_str = parsed_macro.resolve(builtin_vars, self.secrets_manager)
            except MacroResolutionError as e:
                msg = f"Failed to resolve directory '{directory_name}' macro: {e}"
                raise RuntimeError(msg) from e

            # Make absolute (resolve relative paths against project root)
            resolved_dir_path = Path(resolved_path_str)
            if not resolved_dir_path.is_absolute():
                resolved_dir_path = (project_path.parent / resolved_dir_path).resolve()

            # Check if absolute_path is inside this directory
            try:
                # relative_to will raise ValueError if not a subpath
                _ = absolute_path.relative_to(resolved_dir_path)
                # Track the match with its prefix length (for longest match)
                matches.append(
                    DirectoryMatch(
                        directory_name=directory_name,
                        resolved_path=resolved_dir_path,
                        prefix_length=len(resolved_dir_path.parts),
                    )
                )
            except ValueError:
                # Not a subpath, skip
                continue

        if not matches:
            return None

        # Use longest prefix match (most specific directory)
        best_match = matches[0]
        for match in matches:
            if match.prefix_length > best_match.prefix_length:
                best_match = match

        # Calculate relative path from the matched directory
        relative_path = absolute_path.relative_to(best_match.resolved_path)

        # Convert to macro form
        if str(relative_path) == ".":
            # File is directly in the directory root
            # Example: /Users/james/project/outputs → {outputs}
            return f"{{{best_match.directory_name}}}"

        # File is in a subdirectory
        # Example: /Users/james/project/outputs/renders/final.png → {outputs}/renders/final.png
        return f"{{{best_match.directory_name}}}/{relative_path.as_posix()}"

    def on_get_state_for_macro_request(  # noqa: C901
        self, request: GetStateForMacroRequest
    ) -> GetStateForMacroResultSuccess | GetStateForMacroResultFailure:
        """Analyze a macro and return comprehensive state information.

        Flow:
        1. Get current project via GetCurrentProjectRequest
        2. Get template from current project
        3. For each variable, determine if it's:
           - A directory (from template)
           - User-provided (from request)
           - A builtin
        4. Check for conflicts:
           - User providing directory name
           - User overriding builtin with different value
        5. Calculate what's satisfied vs missing
        6. Determine if resolution would succeed
        """
        current_project_request = GetCurrentProjectRequest()
        current_project_result = self.on_get_current_project_request(current_project_request)

        if not isinstance(current_project_result, GetCurrentProjectResultSuccess):
            return GetStateForMacroResultFailure(
                result_details="Attempted to analyze macro state. Failed because no current project is set",
            )

        project_path = current_project_result.project_path
        if project_path is None:
            return GetStateForMacroResultFailure(
                result_details="Attempted to analyze macro state. Failed because no current project is set",
            )

        template = self.successful_templates.get(project_path)
        if template is None:
            return GetStateForMacroResultFailure(
                result_details="Attempted to analyze macro state. Failed because current project template is not loaded",
            )

        all_variables = request.parsed_macro.get_variables()
        directory_names = set(template.directories.keys())
        user_provided_names = set(request.variables.keys())

        satisfied_variables: set[str] = set()
        missing_required_variables: set[str] = set()
        conflicting_variables: set[str] = set()

        for var_info in all_variables:
            var_name = var_info.name

            if var_name in directory_names:
                satisfied_variables.add(var_name)
                if var_name in user_provided_names:
                    conflicting_variables.add(var_name)

            if var_name in user_provided_names:
                satisfied_variables.add(var_name)

            if var_name in BUILTIN_VARIABLES:
                try:
                    builtin_value = self._get_builtin_variable_value(var_name, project_path)
                except (RuntimeError, NotImplementedError) as e:
                    return GetStateForMacroResultFailure(
                        result_details=f"Attempted to analyze macro state. Failed because builtin variable '{var_name}' cannot be resolved: {e}",
                    )

                satisfied_variables.add(var_name)
                if var_name in user_provided_names:
                    user_value = str(request.variables[var_name])
                    if user_value != builtin_value:
                        conflicting_variables.add(var_name)

            if var_info.is_required and var_name not in satisfied_variables:
                missing_required_variables.add(var_name)

        can_resolve = len(missing_required_variables) == 0 and len(conflicting_variables) == 0

        return GetStateForMacroResultSuccess(
            all_variables=all_variables,
            satisfied_variables=satisfied_variables,
            missing_required_variables=missing_required_variables,
            conflicting_variables=conflicting_variables,
            can_resolve=can_resolve,
            result_details=f"Analyzed macro with {len(all_variables)} variables: {len(satisfied_variables)} satisfied, {len(missing_required_variables)} missing, {len(conflicting_variables)} conflicting",
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

    def on_get_all_situations_for_project_request(
        self, request: GetAllSituationsForProjectRequest
    ) -> GetAllSituationsForProjectResultSuccess | GetAllSituationsForProjectResultFailure:
        """Get all situation names and schemas from a project template."""
        template_info = self.registered_template_status.get(request.project_path)

        if template_info is None:
            self._load_system_defaults()
            template_info = self.registered_template_status.get(request.project_path)

        if template_info is None or template_info.status != ProjectValidationStatus.GOOD:
            return GetAllSituationsForProjectResultFailure(
                result_details=f"Attempted to get all situations for project '{request.project_path}'. Failed because project template not available or invalid"
            )

        template = self.successful_templates[request.project_path]
        situations = {situation_name: situation.macro for situation_name, situation in template.situations.items()}

        return GetAllSituationsForProjectResultSuccess(
            situations=situations,
            result_details=f"Successfully retrieved all situations for project '{request.project_path}'. Found {len(situations)} situations",
        )

    # Helper methods (private)

    def _get_parsed_situation_macro(self, project_path: Path, situation_name: str, macro_str: str) -> ParsedMacro:
        """Get or create cached ParsedMacro for a situation.

        Args:
            project_path: Path to the project template
            situation_name: Name of the situation
            macro_str: The macro string to parse

        Returns:
            Cached or newly parsed ParsedMacro instance
        """
        cache_key = SituationMacroKey(project_path=project_path, situation_name=situation_name)

        if cache_key not in self.parsed_situation_schemas:
            self.parsed_situation_schemas[cache_key] = ParsedMacro(macro_str)

        return self.parsed_situation_schemas[cache_key]

    def _get_parsed_directory_macro(self, project_path: Path, directory_name: str, macro_str: str) -> ParsedMacro:
        """Get or create cached ParsedMacro for a directory.

        Args:
            project_path: Path to the project template
            directory_name: Name of the directory
            macro_str: The macro string to parse

        Returns:
            Cached or newly parsed ParsedMacro instance
        """
        cache_key = DirectoryMacroKey(project_path=project_path, directory_name=directory_name)

        if cache_key not in self.parsed_directory_schemas:
            self.parsed_directory_schemas[cache_key] = ParsedMacro(macro_str)

        return self.parsed_directory_schemas[cache_key]

    def _populate_macro_caches_for_template(self, project_path: Path, template: ProjectTemplate) -> None:
        """Pre-populate macro caches for all situations and directories in a template.

        Args:
            project_path: Path to the project template
            template: The loaded project template

        Raises:
            MacroSyntaxError: If any situation or directory macro has invalid syntax
        """
        # Cache all situation macros - fail fast on invalid syntax
        for situation_name, situation in template.situations.items():
            cache_key = SituationMacroKey(project_path=project_path, situation_name=situation_name)
            if cache_key not in self.parsed_situation_schemas:
                self.parsed_situation_schemas[cache_key] = ParsedMacro(situation.macro)

        # Cache all directory macros - fail fast on invalid syntax
        for directory_name, directory_def in template.directories.items():
            cache_key = DirectoryMacroKey(project_path=project_path, directory_name=directory_name)
            if cache_key not in self.parsed_directory_schemas:
                self.parsed_directory_schemas[cache_key] = ParsedMacro(directory_def.path_macro)

    def _get_builtin_variable_value(self, var_name: str, project_path: Path) -> str:
        """Get the value of a single builtin variable.

        Args:
            var_name: Name of the builtin variable
            project_path: Path to the current project template

        Returns:
            String value of the builtin variable

        Raises:
            ValueError: If var_name is not a recognized builtin variable
            NotImplementedError: If builtin variable is not yet implemented
        """
        match var_name:
            case "project_dir":
                return str(project_path.parent)

            case "project_name":
                msg = f"{BUILTIN_PROJECT_NAME} not yet implemented"
                raise NotImplementedError(msg)

            case "workspace_dir":
                config_manager = GriptapeNodes.ConfigManager()
                workspace_dir = config_manager.get_config_value("workspace.directory")
                return str(workspace_dir)

            case "workflow_name":
                context_manager = GriptapeNodes.ContextManager()
                if not context_manager.has_current_workflow():
                    msg = "No current workflow"
                    raise RuntimeError(msg)
                return context_manager.get_current_workflow_name()

            case "workflow_dir":
                msg = f"{BUILTIN_WORKFLOW_DIR} not yet implemented"
                raise NotImplementedError(msg)

            case _:
                msg = f"Unknown builtin variable: {var_name}"
                raise ValueError(msg)

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

        # Populate macro caches for performance
        self._populate_macro_caches_for_template(SYSTEM_DEFAULTS_KEY, DEFAULT_PROJECT_TEMPLATE)
