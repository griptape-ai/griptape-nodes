"""ProjectManager - Manages project templates and file save situations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from pydantic import ValidationError

from griptape_nodes.common.macro_parser import (
    MacroMatchFailure,
    MacroMatchFailureReason,
    MacroResolutionError,
    MacroResolutionFailureReason,
    MacroVariables,
    ParsedMacro,
)
from griptape_nodes.common.project_templates import (
    DEFAULT_PROJECT_TEMPLATE,
    DirectoryDefinition,
    ProjectTemplate,
    ProjectValidationInfo,
    ProjectValidationStatus,
    SituationTemplate,
    load_partial_project_template,
)
from griptape_nodes.files.file import File, FileLoadError, FileWriteError
from griptape_nodes.files.path_utils import canonicalize_for_identity, resolve_file_path, resolve_path_safely
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.library_events import (
    ReloadAllLibrariesRequest,
    ReloadAllLibrariesResultFailure,
)
from griptape_nodes.retained_mode.events.os_events import ReadFileRequest, ReadFileResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultFailure,
    AttemptMapAbsolutePathToProjectResultSuccess,
    AttemptMatchPathAgainstMacroRequest,
    AttemptMatchPathAgainstMacroResultFailure,
    AttemptMatchPathAgainstMacroResultSuccess,
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
    ListProjectTemplatesRequest,
    ListProjectTemplatesResultSuccess,
    LoadProjectTemplateRequest,
    LoadProjectTemplateResultFailure,
    LoadProjectTemplateResultSuccess,
    PathResolutionFailureReason,
    ProjectTemplateInfo,
    SaveProjectTemplateRequest,
    SaveProjectTemplateResultFailure,
    SaveProjectTemplateResultSuccess,
    SetCurrentProjectRequest,
    SetCurrentProjectResultFailure,
    SetCurrentProjectResultSuccess,
    UnregisterProjectTemplateRequest,
    UnregisterProjectTemplateResultFailure,
    UnregisterProjectTemplateResultSuccess,
    ValidateProjectTemplateRequest,
    ValidateProjectTemplateResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.settings import PROJECTS_TO_REGISTER_KEY

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")

# Type alias for project identifiers
# Usually constructed from file path, but kept opaque to prevent abuse
ProjectID = str

# Synthetic identifier for the system default project template
SYSTEM_DEFAULTS_KEY: ProjectID = "<system-defaults>"

# Filename for workspace-level project template overrides
WORKSPACE_PROJECT_FILE = "griptape-nodes-project.yml"

# Builtin variable name constants
BUILTIN_PROJECT_DIR = "project_dir"
BUILTIN_PROJECT_NAME = "project_name"
BUILTIN_WORKSPACE_DIR = "workspace_dir"
BUILTIN_WORKFLOW_NAME = "workflow_name"
BUILTIN_WORKFLOW_DIR = "workflow_dir"
BUILTIN_STATIC_FILES_DIR = "static_files_dir"


@dataclass(frozen=True)
class BuiltinVariableInfo:
    """Metadata about a builtin variable.

    Attributes:
        name: The variable name (e.g., "project_dir")
        is_directory: Whether this variable represents a directory path
    """

    name: str
    is_directory: bool


# Builtin variable definitions with metadata
_BUILTIN_VARIABLE_DEFINITIONS = [
    BuiltinVariableInfo(name=BUILTIN_PROJECT_DIR, is_directory=True),
    BuiltinVariableInfo(name=BUILTIN_PROJECT_NAME, is_directory=False),
    BuiltinVariableInfo(name=BUILTIN_WORKSPACE_DIR, is_directory=True),
    BuiltinVariableInfo(name=BUILTIN_WORKFLOW_NAME, is_directory=False),
    BuiltinVariableInfo(name=BUILTIN_WORKFLOW_DIR, is_directory=True),
    BuiltinVariableInfo(name=BUILTIN_STATIC_FILES_DIR, is_directory=False),
]

# Map of variable name to metadata
_BUILTIN_VARIABLE_INFO: dict[str, BuiltinVariableInfo] = {var.name: var for var in _BUILTIN_VARIABLE_DEFINITIONS}

# Builtin variables available in all macros (read-only)
BUILTIN_VARIABLES = frozenset(var.name for var in _BUILTIN_VARIABLE_DEFINITIONS)


@dataclass
class ProjectInfo:
    """Consolidated information about a loaded project.

    Stores all project-related data including template, validation,
    file paths, and cached parsed macros.
    """

    project_id: ProjectID
    project_file_path: Path | None  # None for system defaults or non-file sources
    project_base_dir: Path  # Directory for resolving relative paths ({project_dir})
    template: ProjectTemplate
    validation: ProjectValidationInfo

    # Cached parsed macros (populated during load for performance)
    parsed_situation_schemas: dict[str, ParsedMacro]  # situation_name -> ParsedMacro
    parsed_directory_schemas: dict[str, ParsedMacro]  # directory_name -> ParsedMacro


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
        event_manager: EventManager,
        config_manager: ConfigManager,
        secrets_manager: SecretsManager,
    ) -> None:
        """Initialize the ProjectManager.

        Args:
            event_manager: The EventManager instance to use for event handling
            config_manager: ConfigManager instance for accessing configuration
            secrets_manager: SecretsManager instance for macro resolution
        """
        self._config_manager = config_manager
        self._secrets_manager = secrets_manager

        # Consolidated project information storage
        self._successfully_loaded_project_templates: dict[ProjectID, ProjectInfo] = {}
        self._current_project_id: ProjectID | None = None
        # Set to True at end of on_app_initialization_complete. Guards workspace switch
        # logic so expensive reloads don't fire during startup.
        self._initialization_complete: bool = False

        # Track validation status for ALL load attempts (including MISSING/UNUSABLE)
        # This allows UI to query why a project failed to load
        self._registered_template_status: dict[Path, ProjectValidationInfo] = {}

        # Register event handlers
        event_manager.assign_manager_to_request_type(LoadProjectTemplateRequest, self.on_load_project_template_request)
        event_manager.assign_manager_to_request_type(GetProjectTemplateRequest, self.on_get_project_template_request)
        event_manager.assign_manager_to_request_type(
            ListProjectTemplatesRequest, self.on_list_project_templates_request
        )
        event_manager.assign_manager_to_request_type(GetSituationRequest, self.on_get_situation_request)
        event_manager.assign_manager_to_request_type(GetPathForMacroRequest, self.on_get_path_for_macro_request)
        event_manager.assign_manager_to_request_type(SetCurrentProjectRequest, self.on_set_current_project_request)
        event_manager.assign_manager_to_request_type(GetCurrentProjectRequest, self.on_get_current_project_request)
        event_manager.assign_manager_to_request_type(SaveProjectTemplateRequest, self.on_save_project_template_request)
        event_manager.assign_manager_to_request_type(
            AttemptMatchPathAgainstMacroRequest, self.on_match_path_against_macro_request
        )
        event_manager.assign_manager_to_request_type(GetStateForMacroRequest, self.on_get_state_for_macro_request)
        event_manager.assign_manager_to_request_type(
            GetAllSituationsForProjectRequest, self.on_get_all_situations_for_project_request
        )
        event_manager.assign_manager_to_request_type(
            AttemptMapAbsolutePathToProjectRequest, self.on_attempt_map_absolute_path_to_project_request
        )
        event_manager.assign_manager_to_request_type(
            UnregisterProjectTemplateRequest, self.on_unregister_project_template_request
        )
        event_manager.assign_manager_to_request_type(
            ValidateProjectTemplateRequest, self.on_validate_project_template_request
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
        # Expand ~/env vars and resolve to absolute so the same file always
        # produces the same project_id regardless of how the caller spelled
        # the path (relative vs absolute, ~/ prefix, symlinks, etc.). Both
        # _registered_template_status (keyed by Path) and
        # _successfully_loaded_project_templates (keyed by str project_id) must
        # use the canonical form so dedupe checks line up.
        project_file_path = canonicalize_for_identity(request.project_path)

        read_request = ReadFileRequest(
            file_path=str(project_file_path),
            encoding="utf-8",
            workspace_only=False,
        )
        read_result = GriptapeNodes.handle_request(read_request)

        if read_result.failed():
            validation = ProjectValidationInfo(status=ProjectValidationStatus.MISSING)
            self._registered_template_status[project_file_path] = validation

            return LoadProjectTemplateResultFailure(
                validation=validation,
                result_details=f"Attempted to load project template from '{project_file_path}'. Failed because file not found",
            )

        if not isinstance(read_result, ReadFileResultSuccess):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self._registered_template_status[project_file_path] = validation

            return LoadProjectTemplateResultFailure(
                validation=validation,
                result_details=f"Attempted to load project template from '{project_file_path}'. Failed because file read returned unexpected result type",
            )

        yaml_text = read_result.content
        if not isinstance(yaml_text, str):
            validation = ProjectValidationInfo(status=ProjectValidationStatus.UNUSABLE)
            self._registered_template_status[project_file_path] = validation

            return LoadProjectTemplateResultFailure(
                validation=validation,
                result_details=f"Attempted to load project template from '{project_file_path}'. Failed because template must be text, got binary content",
            )

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        if overlay is None:
            self._registered_template_status[project_file_path] = validation
            return LoadProjectTemplateResultFailure(
                validation=validation,
                result_details=f"Attempted to load project template from '{project_file_path}'. Failed because YAML could not be parsed",
            )

        template = ProjectTemplate.merge(DEFAULT_PROJECT_TEMPLATE, overlay, validation)

        project_id = str(project_file_path)
        project_base_dir = project_file_path.parent

        # Parse all macros BEFORE creating ProjectInfo - collect ALL errors
        situation_schemas = self._parse_situation_macros(template.situations, validation)
        directory_schemas = self._parse_directory_macros(template.directories, validation)

        # Now check if validation is usable after collecting all errors
        if not validation.is_usable():
            self._registered_template_status[project_file_path] = validation
            return LoadProjectTemplateResultFailure(
                validation=validation,
                result_details=f"Attempted to load project template from '{project_file_path}'. Failed because template is not usable (status: {validation.status})",
            )

        # Create consolidated ProjectInfo with fully populated macro caches
        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=project_file_path,
            project_base_dir=project_base_dir,
            template=template,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        # Store in new consolidated dict
        self._successfully_loaded_project_templates[project_id] = project_info

        # Track validation status for all load attempts (for UI display)
        self._registered_template_status[project_file_path] = validation

        # Persist path so the project survives engine restarts
        self._register_project_path(project_id)

        return LoadProjectTemplateResultSuccess(
            project_id=project_id,
            template=template,
            validation=validation,
            result_details=f"Template loaded successfully with status: {validation.status}",
        )

    def on_get_project_template_request(
        self, request: GetProjectTemplateRequest
    ) -> GetProjectTemplateResultSuccess | GetProjectTemplateResultFailure:
        """Get cached template for a project ID."""
        project_info = self._successfully_loaded_project_templates.get(request.project_id)

        if project_info is None:
            return GetProjectTemplateResultFailure(
                result_details=f"Attempted to get project template for '{request.project_id}'. Failed because template not loaded yet",
            )

        return GetProjectTemplateResultSuccess(
            template=project_info.template,
            validation=project_info.validation,
            result_details=f"Successfully retrieved project template for '{request.project_id}'. Status: {project_info.validation.status}",
        )

    def on_list_project_templates_request(
        self, request: ListProjectTemplatesRequest
    ) -> ListProjectTemplatesResultSuccess:
        """List all project templates that have been loaded or attempted to load.

        Returns separate lists for successfully loaded and failed templates.
        """
        successfully_loaded: list[ProjectTemplateInfo] = []
        failed_to_load: list[ProjectTemplateInfo] = []

        # Gather successfully loaded templates from _successfully_loaded_project_templates
        for project_id, project_info in self._successfully_loaded_project_templates.items():
            # Skip system builtins unless requested
            if not request.include_system_builtins and project_id == SYSTEM_DEFAULTS_KEY:
                continue

            successfully_loaded.append(
                ProjectTemplateInfo(
                    project_id=project_id, validation=project_info.validation, name=project_info.template.name
                )
            )

        # Gather failed templates from _registered_template_status
        # These are tracked by Path, not ProjectID
        for template_path, validation in self._registered_template_status.items():
            project_id = str(template_path)

            # Skip if already in successfully loaded (validation status might be FLAWED but still loaded)
            if project_id in self._successfully_loaded_project_templates:
                continue

            # Skip system builtins unless requested
            if not request.include_system_builtins and project_id == SYSTEM_DEFAULTS_KEY:
                continue

            # Only include if status indicates failure (UNUSABLE or MISSING)
            if not validation.is_usable():
                failed_to_load.append(ProjectTemplateInfo(project_id=project_id, validation=validation))

        return ListProjectTemplatesResultSuccess(
            successfully_loaded=successfully_loaded,
            failed_to_load=failed_to_load,
            result_details=f"Successfully listed project templates. Loaded: {len(successfully_loaded)}, Failed: {len(failed_to_load)}",
        )

    def on_get_situation_request(
        self, request: GetSituationRequest
    ) -> GetSituationResultSuccess | GetSituationResultFailure:
        """Get the complete situation template for a specific situation.

        Returns the full SituationTemplate including macro and policy.

        Flow:
        1. Get current project
        2. Get template from successful_templates
        3. Get situation from template
        4. Return complete SituationTemplate
        """
        current_project_request = GetCurrentProjectRequest()
        current_project_result = self.on_get_current_project_request(current_project_request)

        if not isinstance(current_project_result, GetCurrentProjectResultSuccess):
            return GetSituationResultFailure(
                result_details=f"Attempted to get situation '{request.situation_name}'. Failed because no current project is set or template not loaded",
            )

        template = current_project_result.project_info.template

        situation = template.situations.get(request.situation_name)
        if situation is None:
            return GetSituationResultFailure(
                result_details=f"Attempted to get situation '{request.situation_name}'. Failed because situation not found",
            )

        return GetSituationResultSuccess(
            situation=situation,
            result_details=f"Successfully retrieved situation '{request.situation_name}'. Macro: {situation.macro}, Policy: create_dirs={situation.policy.create_dirs}, on_collision={situation.policy.on_collision}",
        )

    def on_get_path_for_macro_request(  # noqa: C901, PLR0911, PLR0912, PLR0915
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
                result_details="Attempted to resolve macro path. Failed because no current project is set or template not loaded",
            )

        project_info = current_project_result.project_info
        template = project_info.template

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

        resolution_bag: MacroVariables = {}
        disallowed_overrides: set[str] = set()
        # Per-request cache: dedupes work when the macro references the same
        # directory multiple times (or via multiple paths through nested refs).
        directory_resolution_cache: dict[str, str] = {}

        for var_info in variable_infos:
            var_name = var_info.name

            if var_name in directory_names:
                # Recursively resolve so nested directory references (e.g.
                # watch_outputs -> watch_folder) expand to a concrete path
                # instead of leaking literal {...} tokens into the result.
                # User vars flow through so directory macros can reference
                # caller-supplied values just like situation macros do.
                try:
                    resolution_bag[var_name] = self._resolve_directory_path(
                        var_name, project_info, directory_resolution_cache, set(), request.variables
                    )
                except (RuntimeError, NotImplementedError) as e:
                    # NotImplementedError: directory references an unimplemented builtin (e.g. {project_name}).
                    # RuntimeError: cycle, unknown reference, or inner MacroResolutionError.
                    return GetPathForMacroResultFailure(
                        failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                        result_details=f"Attempted to resolve macro path. Failed because directory '{var_name}' could not be resolved: {e}",
                    )
            elif var_name in user_provided_names:
                resolution_bag[var_name] = request.variables[var_name]

            if var_name in BUILTIN_VARIABLES:
                try:
                    builtin_value = self._get_builtin_variable_value(var_name, project_info)
                except (RuntimeError, NotImplementedError) as e:
                    if not var_info.is_required:
                        continue
                    return GetPathForMacroResultFailure(
                        failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
                        result_details=f"Attempted to resolve macro path. Failed because builtin variable '{var_name}' cannot be resolved: {e}",
                    )
                # Confirm no monkey business with trying to override builtin values
                existing = resolution_bag.get(var_name)
                if existing is not None:
                    # For directory builtin variables, compare as resolved paths
                    builtin_info = _BUILTIN_VARIABLE_INFO.get(var_name)
                    if builtin_info and builtin_info.is_directory:
                        resolved_existing = resolve_path_safely(Path(str(existing)))
                        resolved_builtin = resolve_path_safely(Path(builtin_value))
                        if resolved_existing != resolved_builtin:
                            disallowed_overrides.add(var_name)
                    elif str(existing) != builtin_value:
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

        try:
            resolved_string = request.parsed_macro.resolve(resolution_bag, self._secrets_manager)
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

        # Make absolute path by resolving against the workspace directory.
        # resolve_file_path handles ~, env vars, and absolute paths in addition to relative paths.
        workspace_path = self._config_manager.workspace_path
        absolute_path = resolve_file_path(resolved_string, workspace_path)

        return GetPathForMacroResultSuccess(
            resolved_path=resolved_path,
            absolute_path=absolute_path,
            result_details=f"Successfully resolved macro path. Result: {resolved_path}",
        )

    def _find_workspace_override(self, project_file_path: Path, project_workspaces: dict[str, str]) -> str | None:
        """Return the user-configured workspace override for a project file, or None if not mapped."""
        resolved_project_path = str(canonicalize_for_identity(project_file_path))
        return next(
            (v for k, v in project_workspaces.items() if str(canonicalize_for_identity(k)) == resolved_project_path),
            None,
        )

    async def _reload_after_project_switch(
        self, project_id: str | None, *, workspace_changed: bool
    ) -> SetCurrentProjectResultFailure | None:
        """Reload libraries and optionally re-register workflows after a project switch.

        Always reloads libraries (project config can affect env vars and library behavior).
        Only re-registers workflows when the workspace directory actually changed.

        Returns a failure result if library reload fails, otherwise None.
        """
        reload_result = await GriptapeNodes.ahandle_request(ReloadAllLibrariesRequest())
        if isinstance(reload_result, ReloadAllLibrariesResultFailure):
            return SetCurrentProjectResultFailure(
                result_details=f"Attempted to set project '{project_id}'. "
                f"Config updated but library reload failed: {reload_result.result_details}",
            )
        if workspace_changed:
            GriptapeNodes.WorkflowManager().refresh_workflow_registry()
        return None

    async def on_set_current_project_request(
        self, request: SetCurrentProjectRequest
    ) -> SetCurrentProjectResultSuccess | SetCurrentProjectResultFailure:
        """Set which project user has selected.

        Captures workspace path before and after config layer changes. If the
        workspace actually changed and startup is complete, performs an expensive
        workspace switch: reloads all libraries and re-registers workflows.
        During startup, LibraryManager handles library loading concurrently, so
        the workspace switch is skipped.
        """
        # Capture workspace BEFORE config changes for comparison after
        old_workspace = self._config_manager.workspace_path

        self._current_project_id = request.project_id

        if request.project_id is not None:
            project_info = self._successfully_loaded_project_templates.get(request.project_id)
            if project_info is not None and project_info.project_file_path is not None:
                project_file_path = project_info.project_file_path
                project_dir = project_file_path.parent
                self._config_manager.load_project_config(project_dir)

                # Determine workspace directory using the following priority:
                # 1. project_workspaces in user config (per-user, per-project override)
                # 2. workspace_directory in project-adjacent config (shared project default)
                # 3. env vars
                # 4. Auto-default to project directory
                project_workspaces = self._config_manager.get_config_value(
                    "project_workspaces",
                    config_source="user_config",
                    default={},
                )
                workspace_override = self._find_workspace_override(project_file_path, project_workspaces)

                if workspace_override is not None:
                    self._config_manager.set_workspace_override(Path(workspace_override))
                elif (
                    "workspace_directory" not in self._config_manager.project_config
                    and "workspace_directory" not in self._config_manager.env_config
                ):
                    # If neither the project-adjacent config nor env vars explicitly set
                    # workspace_directory, default the workspace to the project directory itself.
                    self._config_manager.set_workspace_override(project_dir)

                # Load workspace config layer from the resolved workspace directory.
                self._config_manager.load_workspace_config(self._config_manager.workspace_path)
            elif project_info is not None and project_info.project_file_path is None:
                # Switching to system defaults: clear any project-specific workspace override
                # and reload configs so workspace_path resolves from default config layers.
                self._config_manager.set_workspace_override(None)
                self._config_manager.load_configs()

        new_workspace = self._config_manager.workspace_path
        workspace_changed = old_workspace != new_workspace

        if self._initialization_complete:
            failure = await self._reload_after_project_switch(request.project_id, workspace_changed=workspace_changed)
            if failure is not None:
                return failure

        if request.project_id is None:
            return SetCurrentProjectResultSuccess(
                result_details="Successfully set current project. No project selected",
            )

        result = SetCurrentProjectResultSuccess(
            result_details=f"Successfully set current project. ID: {request.project_id}",
        )
        if workspace_changed and self._initialization_complete:
            result.altered_workflow_state = True
        return result

    def on_get_current_project_request(
        self, _request: GetCurrentProjectRequest
    ) -> GetCurrentProjectResultSuccess | GetCurrentProjectResultFailure:
        """Get currently selected project with template info."""
        if self._current_project_id is None:
            return GetCurrentProjectResultFailure(
                result_details="Attempted to get current project. Failed because no project is currently set"
            )

        project_info = self._successfully_loaded_project_templates.get(self._current_project_id)
        if project_info is None:
            return GetCurrentProjectResultFailure(
                result_details=f"Attempted to get current project. Failed because project not found for ID: '{self._current_project_id}'"
            )

        return GetCurrentProjectResultSuccess(
            project_info=project_info,
            result_details=f"Successfully retrieved current project. ID: {self._current_project_id}",
        )

    def on_save_project_template_request(
        self, request: SaveProjectTemplateRequest
    ) -> SaveProjectTemplateResultSuccess | SaveProjectTemplateResultFailure:
        """Save user customizations to project.yml.

        Flow:
        1. Validate template_data as a ProjectTemplate model
        2. Serialize to YAML using ProjectTemplate.to_overlay_yaml()
        3. Write to disk via File.write_text
        4. Invalidate cache (force reload on next access)
        """
        # Step 1: Validate and parse template_data
        try:
            template = ProjectTemplate.model_validate(request.template_data)
        except ValidationError as e:
            return SaveProjectTemplateResultFailure(
                result_details=f"Attempted to save project template to '{request.project_path}'. Failed because template data is invalid: {e}",
            )

        # Step 2: Serialize to YAML
        try:
            yaml_content = template.to_overlay_yaml(DEFAULT_PROJECT_TEMPLATE)
        except Exception as e:
            return SaveProjectTemplateResultFailure(
                result_details=f"Attempted to save project template to '{request.project_path}'. Failed because YAML serialization failed: {e}",
            )

        # Step 3: Write to disk
        try:
            File(str(request.project_path)).write_text(yaml_content)
        except FileWriteError as e:
            return SaveProjectTemplateResultFailure(
                result_details=f"Attempted to save project template to '{request.project_path}'. Failed because file write failed: {e}",
            )

        # Step 4: Invalidate cache so next LoadProjectTemplateRequest reads from disk
        project_id: ProjectID = str(request.project_path)
        self._successfully_loaded_project_templates.pop(project_id, None)
        self._registered_template_status.pop(request.project_path, None)

        return SaveProjectTemplateResultSuccess(
            result_details=f"Successfully saved project template to '{request.project_path}'",
        )

    def on_validate_project_template_request(
        self, request: ValidateProjectTemplateRequest
    ) -> ValidateProjectTemplateResultSuccess:
        """Dry-run validate a template dict.

        Runs the same validation the load path runs (pydantic model validation
        plus macro parsing for situations and directories), but does not touch
        disk or the template registry. Always returns Success; callers inspect
        `validation.status` to decide whether the template is usable.
        """
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        try:
            template = ProjectTemplate.model_validate(request.template_data)
        except ValidationError as e:
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                validation.add_error(field_path=field_path, message=error["msg"])
            return ValidateProjectTemplateResultSuccess(
                validation=validation,
                result_details=f"Template validation failed with {len(validation.problems)} problem(s)",
            )

        self._parse_situation_macros(template.situations, validation)
        self._parse_directory_macros(template.directories, validation)

        if validation.status == ProjectValidationStatus.GOOD:
            details = "Template is valid"
        else:
            details = f"Template validation found {len(validation.problems)} problem(s) (status: {validation.status})"
        return ValidateProjectTemplateResultSuccess(validation=validation, result_details=details)

    def on_unregister_project_template_request(
        self, request: UnregisterProjectTemplateRequest
    ) -> UnregisterProjectTemplateResultSuccess | UnregisterProjectTemplateResultFailure:
        """Remove a registered project template from in-memory caches and persisted config.

        Flow:
        1. Verify the project_id is known
        2. Remove from _successfully_loaded_project_templates and _registered_template_status
        3. Remove from PROJECTS_TO_REGISTER_KEY in user config
        4. If this was the current project, clear the current project
        """
        project_id = request.project_id

        if (
            project_id not in self._successfully_loaded_project_templates
            and Path(project_id) not in self._registered_template_status
        ):
            return UnregisterProjectTemplateResultFailure(
                result_details=f"Attempted to unregister project template '{project_id}'. Failed because it is not registered.",
            )

        # Remove from in-memory caches
        self._successfully_loaded_project_templates.pop(project_id, None)
        self._registered_template_status.pop(Path(project_id), None)

        # Remove from persisted config so it is not reloaded on restart
        try:
            registered: list[str] = self._config_manager.get_config_value(PROJECTS_TO_REGISTER_KEY, default=[]) or []
            updated = [p for p in registered if p != project_id]
            self._config_manager.set_config_value(PROJECTS_TO_REGISTER_KEY, updated)
        except Exception:
            logger.warning("Failed to remove project path '%s' from persisted config", project_id)

        # If this was the active project, clear the current project
        if self._current_project_id == project_id:
            self._current_project_id = None

        return UnregisterProjectTemplateResultSuccess(
            result_details=f"Successfully unregistered project template '{project_id}'",
        )

    def on_match_path_against_macro_request(
        self, request: AttemptMatchPathAgainstMacroRequest
    ) -> AttemptMatchPathAgainstMacroResultSuccess | AttemptMatchPathAgainstMacroResultFailure:
        """Attempt to match a path against a macro schema and extract variables.

        Flow:
        1. Check secrets manager is available (failure = true error)
        2. Call ParsedMacro.extract_variables() with path and known variables
        3. If match succeeds, return success with extracted_variables
        4. If match fails, return success with match_failure (not an error)
        """
        extracted = request.parsed_macro.extract_variables(
            request.file_path,
            request.known_variables,
            self._secrets_manager,
        )

        if extracted is None:
            # Pattern didn't match - this is a normal outcome, not an error
            return AttemptMatchPathAgainstMacroResultSuccess(
                extracted_variables=None,
                match_failure=MacroMatchFailure(
                    failure_reason=MacroMatchFailureReason.STATIC_TEXT_MISMATCH,
                    expected_pattern=request.parsed_macro.template,
                    known_variables_used=request.known_variables,
                    error_details=f"Path '{request.file_path}' does not match macro pattern",
                ),
                result_details=f"Attempted to match path '{request.file_path}' against macro '{request.parsed_macro.template}'. Pattern did not match",
            )

        # Pattern matched successfully
        return AttemptMatchPathAgainstMacroResultSuccess(
            extracted_variables=extracted,
            match_failure=None,
            result_details=f"Successfully matched path '{request.file_path}' against macro '{request.parsed_macro.template}'. Extracted {len(extracted)} variables",
        )

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
                result_details="Attempted to analyze macro state. Failed because no current project is set or template not loaded",
            )

        project_info = current_project_result.project_info
        template = project_info.template

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
                    builtin_value = self._get_builtin_variable_value(var_name, project_info)
                except (RuntimeError, NotImplementedError) as e:
                    if not var_info.is_required:
                        continue
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
        Loads system defaults, then checks workspace for a griptape-nodes-project.yml
        overlay file and sets it as the current project if found.
        """
        self._load_system_defaults()

        # Set system defaults as current project (using synthetic key for system defaults)
        set_request = SetCurrentProjectRequest(project_id=SYSTEM_DEFAULTS_KEY)
        result = await self.on_set_current_project_request(set_request)

        if result.failed():
            logger.error("Failed to set default project as current: %s", result.result_details)
            return

        logger.debug("Successfully loaded default project template")

        # Check workspace for an optional project overlay file
        await self._load_workspace_project()

        # Load any additional project templates previously registered by the user
        self._load_registered_projects()

        # Mark initialization complete so subsequent project switches trigger
        # workspace detection and library reload when the workspace actually changes.
        self._initialization_complete = True

    def on_get_all_situations_for_project_request(
        self, _request: GetAllSituationsForProjectRequest
    ) -> GetAllSituationsForProjectResultSuccess | GetAllSituationsForProjectResultFailure:
        """Get all situation names and schemas from current project template."""
        current_project_request = GetCurrentProjectRequest()
        current_project_result = self.on_get_current_project_request(current_project_request)

        if not isinstance(current_project_result, GetCurrentProjectResultSuccess):
            return GetAllSituationsForProjectResultFailure(
                result_details="Attempted to get all situations. Failed because no current project is set or template not loaded"
            )

        template = current_project_result.project_info.template
        situations = {situation_name: situation.macro for situation_name, situation in template.situations.items()}

        return GetAllSituationsForProjectResultSuccess(
            situations=situations,
            result_details=f"Successfully retrieved all situations. Found {len(situations)} situations",
        )

    def on_attempt_map_absolute_path_to_project_request(
        self, request: AttemptMapAbsolutePathToProjectRequest
    ) -> AttemptMapAbsolutePathToProjectResultSuccess | AttemptMapAbsolutePathToProjectResultFailure:
        """Find out if an absolute path exists anywhere within a Project directory.

        Returns Success with mapped_path if inside project (macro form returned).
        Returns Success with None if outside project (valid answer: "not in project").
        Returns Failure if operation cannot be performed (no project, no secrets manager).

        Args:
            request: Request containing the absolute path to check

        Returns:
            Success with mapped_path if path is inside project
            Success with None if path is outside project
            Failure if operation cannot be performed
        """
        # Check prerequisites - return Failure if missing
        current_project_request = GetCurrentProjectRequest()
        current_project_result = self.on_get_current_project_request(current_project_request)

        if not isinstance(current_project_result, GetCurrentProjectResultSuccess):
            return AttemptMapAbsolutePathToProjectResultFailure(
                result_details="Attempted to map absolute path. Failed because no current project is set"
            )

        project_info = current_project_result.project_info

        # Try to map the path
        try:
            mapped_path = self._absolute_path_to_macro_path(request.absolute_path, project_info)
        except (RuntimeError, NotImplementedError) as e:
            # Variable resolution failed - this is a Failure (can't complete the operation)
            return AttemptMapAbsolutePathToProjectResultFailure(
                result_details=f"Attempted to map absolute path '{request.absolute_path}'. Failed because: {e}"
            )

        # Path successfully checked
        if mapped_path is None:
            # Success: we successfully determined the path is outside project
            return AttemptMapAbsolutePathToProjectResultSuccess(
                mapped_path=None,
                result_details=f"Attempted to map absolute path '{request.absolute_path}'. Path is outside all project directories",
            )

        # Success: path mapped to macro form
        return AttemptMapAbsolutePathToProjectResultSuccess(
            mapped_path=mapped_path,
            result_details=f"Successfully mapped absolute path to '{mapped_path}'",
        )

    # Helper methods (private)

    @staticmethod
    def _parse_situation_macros(
        situations: dict[str, SituationTemplate], validation: ProjectValidationInfo
    ) -> dict[str, ParsedMacro]:
        """Parse all situation macros.

        This is called BEFORE creating ProjectInfo to ensure all macros are valid.
        Collects all parsing errors into the validation object instead of raising.

        Args:
            situations: Dictionary of situation templates to parse
            validation: Validation object to collect errors

        Returns:
            Dictionary mapping situation_name to ParsedMacro (only for successfully parsed macros)
        """
        situation_schemas: dict[str, ParsedMacro] = {}

        for situation_name, situation in situations.items():
            try:
                situation_schemas[situation_name] = ParsedMacro(situation.macro)
            except Exception as e:
                validation.add_error(f"situations.{situation_name}.macro", f"Failed to parse macro: {e}")

        return situation_schemas

    @staticmethod
    def _parse_directory_macros(
        directories: dict[str, DirectoryDefinition], validation: ProjectValidationInfo
    ) -> dict[str, ParsedMacro]:
        """Parse all directory macros.

        This is called BEFORE creating ProjectInfo to ensure all macros are valid.
        Collects all parsing errors into the validation object instead of raising.

        Args:
            directories: Dictionary of directory definitions to parse
            validation: Validation object to collect errors

        Returns:
            Dictionary mapping directory_name to ParsedMacro (only for successfully parsed macros)
        """
        directory_schemas: dict[str, ParsedMacro] = {}

        for directory_name, directory_def in directories.items():
            try:
                directory_schemas[directory_name] = ParsedMacro(directory_def.path_macro)
            except Exception as e:
                validation.add_error(f"directories.{directory_name}.path_macro", f"Failed to parse macro: {e}")

        return directory_schemas

    def _get_builtin_variable_value(self, var_name: str, project_info: ProjectInfo) -> str:
        """Get the value of a single builtin variable.

        Args:
            var_name: Name of the builtin variable
            project_info: Information about the current project

        Returns:
            String value of the builtin variable

        Raises:
            ValueError: If var_name is not a recognized builtin variable
            NotImplementedError: If builtin variable is not yet implemented
        """
        match var_name:
            case "project_dir":
                return str(project_info.project_base_dir)

            case "project_name":
                msg = f"{BUILTIN_PROJECT_NAME} not yet implemented"
                raise NotImplementedError(msg)

            case "workspace_dir":
                return str(self._config_manager.workspace_path)

            case "workflow_name":
                context_manager = GriptapeNodes.ContextManager()
                if not context_manager.has_current_workflow():
                    msg = "No current workflow"
                    raise RuntimeError(msg)
                return context_manager.get_current_workflow_name()

            case "workflow_dir":
                context_manager = GriptapeNodes.ContextManager()
                if not context_manager.has_current_workflow():
                    msg = "No current workflow"
                    raise RuntimeError(msg)
                workflow_name = context_manager.get_current_workflow_name()
                try:
                    workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)
                except KeyError as e:
                    msg = f"Workflow '{workflow_name}' has not been saved yet"
                    raise RuntimeError(msg) from e
                workflow_file_path = Path(WorkflowRegistry.get_complete_file_path(workflow.file_path))
                return str(workflow_file_path.parent)

            case "static_files_dir":
                return self._config_manager.get_config_value("static_files_directory", default="staticfiles")

            case _:
                msg = f"Unknown builtin variable: {var_name}"
                raise ValueError(msg)

    def _resolve_directory_path(  # noqa: C901
        self,
        directory_name: str,
        project_info: ProjectInfo,
        cache: dict[str, str],
        visiting: set[str],
        user_variables: MacroVariables,
    ) -> str:
        """Recursively resolve a directory macro into a fully substituted path string.

        Directory ``path_macro`` values can reference other directories, builtin
        variables (e.g. ``watch_outputs: "{watch_folder}/outputs"``), or
        user-supplied variables from the outer request. This helper walks the
        reference chain and substitutes each token with its resolved value so
        the returned string contains no ``{...}`` tokens. Without this, a
        situation that references a chained directory would emit the literal
        inner token (e.g. ``{watch_folder}/outputs/...``) into the final path.

        Mirrors the optional/required handling of the top-level macro handler:
        an optional builtin that fails to resolve is dropped (segment omitted);
        a required one propagates the error.

        Args:
            directory_name: Name of the directory to resolve.
            project_info: Current project info (supplies parsed schemas and builtins).
            cache: Memoization cache keyed by directory name; shared across a
                single resolution pass so each directory is resolved at most once.
            visiting: Names currently on the recursion stack; a re-entry signals
                a cycle.
            user_variables: Variables from the outer request, available for
                substitution inside directory macros (empty dict when there
                is no caller context, e.g. absolute-path mapping).

        Returns:
            Fully resolved path string with every ``{...}`` token substituted.

        Raises:
            RuntimeError: If a cycle is detected, a referenced directory is
                unknown, a required builtin/nested macro fails to resolve, or
                ``ParsedMacro.resolve`` raises (e.g. required token missing).
            NotImplementedError: If a required builtin is not yet implemented
                (e.g. ``{project_name}`` as of today).
        """
        # Memoized: a directory referenced multiple times in one request resolves once.
        if directory_name in cache:
            return cache[directory_name]

        # Re-entry = cycle (a -> b -> a). Without this guard recursion would never terminate.
        if directory_name in visiting:
            chain = " -> ".join([*visiting, directory_name])
            msg = f"Cycle detected while resolving directory '{directory_name}' (chain: {chain})"
            raise RuntimeError(msg)

        parsed_macro = project_info.parsed_directory_schemas.get(directory_name)
        if parsed_macro is None:
            msg = f"Directory '{directory_name}' not found in parsed schemas"
            raise RuntimeError(msg)

        visiting.add(directory_name)
        try:
            # Build a variables bag for this directory's macro by resolving each
            # referenced token. Nested directories recurse; builtins are queried
            # at call time so live context (workflow, workspace) is reflected;
            # user-supplied variables flow through so directory macros can be as
            # expressive as situation macros.
            inner_bag: MacroVariables = {}
            for var_info in parsed_macro.get_variables():
                var_name = var_info.name
                if var_name in project_info.parsed_directory_schemas:
                    inner_bag[var_name] = self._resolve_directory_path(
                        var_name, project_info, cache, visiting, user_variables
                    )
                elif var_name in BUILTIN_VARIABLES:
                    # Mirror top-level behavior: an optional builtin that cannot
                    # be resolved (no current workflow, unimplemented, etc.) is
                    # dropped from the bag so ParsedMacro.resolve() omits the
                    # whole optional segment. Required builtins still surface.
                    try:
                        inner_bag[var_name] = self._get_builtin_variable_value(var_name, project_info)
                    except (RuntimeError, NotImplementedError):
                        if var_info.is_required:
                            raise
                        continue
                elif var_name in user_variables:
                    inner_bag[var_name] = user_variables[var_name]
                # Else: unknown name, left out of bag. ParsedMacro.resolve drops
                # it if optional, raises MacroResolutionError if required (caught below).

            try:
                resolved = parsed_macro.resolve(inner_bag, self._secrets_manager)
            except MacroResolutionError as e:
                msg = f"Failed to resolve directory '{directory_name}' macro: {e}"
                raise RuntimeError(msg) from e
        finally:
            # Must discard even on raise so a failed sibling doesn't poison the
            # visiting set for a later resolution pass that reuses it.
            visiting.discard(directory_name)

        cache[directory_name] = resolved
        return resolved

    def _absolute_path_to_macro_path(self, absolute_path: Path, project_info: ProjectInfo) -> str | None:
        """Convert an absolute path to macro form using longest prefix matching.

        Resolves all project directories at runtime (to support env vars and macros),
        then checks if the absolute path is within any of them.
        Uses longest prefix matching to find the best match.

        Args:
            absolute_path: Absolute path to convert (e.g., /Users/james/project/outputs/file.png)
            project_info: Information about the current project

        Returns:
            Macro-ified path (e.g., {outputs}/file.png) if inside a project directory,
            or None if outside all project directories

        Raises:
            RuntimeError: If directory resolution fails or builtin variable cannot be resolved
            NotImplementedError: If a required builtin variable is not yet implemented

        Examples:
            /Users/james/project/outputs/renders/file.png → "{outputs}/renders/file.png"
            /Users/james/project/outputs/inputs/file.png → "{outputs}/inputs/file.png"
            /Users/james/Downloads/file.png → None
        """
        # Normalize paths for consistent cross-platform comparison
        absolute_path = resolve_path_safely(absolute_path)

        template = project_info.template
        workspace_dir = resolve_path_safely(self._config_manager.workspace_path)
        project_base_dir = resolve_path_safely(project_info.project_base_dir)

        # Find all matching directories (where absolute_path is inside the directory)
        class DirectoryMatch(NamedTuple):
            directory_name: str
            resolved_path: Path
            prefix_length: int

        matches: list[DirectoryMatch] = []
        # Shared across this sweep so directories referenced by other directories
        # (watch_folder -> watch_outputs) don't get re-resolved per iteration.
        directory_resolution_cache: dict[str, str] = {}

        for directory_name in template.directories:
            # Fully expand nested directory and builtin references so prefix
            # matching compares real paths, not unresolved {...} templates.
            # No user-variable context here — this sweep operates purely on
            # the current project state, independent of any request.
            resolved_path_str = self._resolve_directory_path(
                directory_name, project_info, directory_resolution_cache, set(), {}
            )

            # Make absolute (resolve relative paths against the workspace directory).
            # resolve_file_path handles ~, env vars, and absolute paths in addition to relative paths.
            resolved_dir_path = resolve_file_path(resolved_path_str, workspace_dir)
            # Normalize for consistent cross-platform comparison
            resolved_dir_path = resolve_path_safely(resolved_dir_path)

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

        # If no defined directories matched, try {project_dir} as fallback
        if not matches:
            # Check if path is inside project_base_dir
            try:
                relative_path = absolute_path.relative_to(project_base_dir)

                # Convert to {project_dir} macro form
                if str(relative_path) == ".":
                    return "{project_dir}"
                return f"{{project_dir}}/{relative_path.as_posix()}"
            except ValueError:
                # Not inside project_base_dir either
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

    # Private helper methods

    def _load_system_defaults(self) -> None:
        """Load bundled system default template.

        System defaults are now defined in Python as DEFAULT_PROJECT_TEMPLATE.
        This is always valid by construction.
        """
        logger.debug("Loading system default template")

        # Create validation info to track that defaults were loaded
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        # System defaults use workspace directory as the base directory.
        workspace_dir = self._config_manager.workspace_path

        # Parse all macros BEFORE creating ProjectInfo (system defaults should always be valid)
        situation_schemas = self._parse_situation_macros(DEFAULT_PROJECT_TEMPLATE.situations, validation)
        directory_schemas = self._parse_directory_macros(DEFAULT_PROJECT_TEMPLATE.directories, validation)

        # Create consolidated ProjectInfo with fully populated macro caches
        project_info = ProjectInfo(
            project_id=SYSTEM_DEFAULTS_KEY,
            project_file_path=None,  # No actual file for system defaults
            project_base_dir=workspace_dir,  # Use workspace as base
            template=DEFAULT_PROJECT_TEMPLATE,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )

        # Store in new consolidated dict
        self._successfully_loaded_project_templates[SYSTEM_DEFAULTS_KEY] = project_info

        logger.debug("System defaults loaded successfully")

    def _resolve_project_file_path(self) -> Path | None:
        """Resolve the path to the project file to load, or None if no file should be loaded.

        Checks config in the following order:
        1. The path specified by the `project_file` config setting (if set)
        2. griptape-nodes-project.yml in the workspace directory (default)

        Returns None if no project file should be loaded (missing config, file not found).
        """
        project_file_value = self._config_manager.get_config_value("project_file")
        if project_file_value is not None:
            project_path = Path(project_file_value)
            if project_path.exists():
                return project_path
            logger.warning(
                "project_file config points to '%s' which does not exist, falling back to workspace default",
                project_path,
            )

        workspace_dir = self._config_manager.workspace_path
        workspace_project_path = workspace_dir / WORKSPACE_PROJECT_FILE
        if not workspace_project_path.exists():
            logger.debug("No workspace project file found at '%s'", workspace_project_path)
            return None

        return workspace_project_path

    async def _load_workspace_project(self) -> None:
        """Load workspace-level project template overlay if present.

        Checks for a project file using _resolve_project_file_path. If found, loads
        it as an overlay on top of system defaults and sets it as the current project.
        If no file is found, the system defaults remain current.
        """
        workspace_project_path = self._resolve_project_file_path()
        if workspace_project_path is None:
            return

        workspace_project_path = workspace_project_path.resolve()
        logger.info("Found workspace project file at '%s', loading", workspace_project_path)

        try:
            yaml_text = File(str(workspace_project_path)).read_text()
        except FileLoadError as e:
            logger.error(
                "Attempted to read workspace project file at '%s'. Failed with: %s",
                workspace_project_path,
                e.result_details,
            )
            return

        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)
        overlay = load_partial_project_template(yaml_text, validation)

        if overlay is None:
            logger.error(
                "Attempted to load workspace project from '%s'. Failed because YAML could not be parsed",
                workspace_project_path,
            )
            return

        template = ProjectTemplate.merge(DEFAULT_PROJECT_TEMPLATE, overlay, validation)

        if not validation.is_usable():
            problem_details = "; ".join(
                f"{p.field_path} (line {p.line_number}): {p.message}"
                if p.line_number is not None
                else f"{p.field_path}: {p.message}"
                for p in validation.problems
            )
            logger.error(
                "Attempted to load workspace project from '%s'. Failed because template is not usable (status: %s). Problems: %s",
                workspace_project_path,
                validation.status,
                problem_details,
            )
            return

        project_id = str(workspace_project_path)
        situation_schemas = self._parse_situation_macros(template.situations, validation)
        directory_schemas = self._parse_directory_macros(template.directories, validation)

        project_info = ProjectInfo(
            project_id=project_id,
            project_file_path=workspace_project_path,
            project_base_dir=workspace_project_path.parent,
            template=template,
            validation=validation,
            parsed_situation_schemas=situation_schemas,
            parsed_directory_schemas=directory_schemas,
        )
        self._successfully_loaded_project_templates[project_id] = project_info
        self._registered_template_status[workspace_project_path] = validation

        set_request = SetCurrentProjectRequest(project_id=project_id)
        set_result = await self.on_set_current_project_request(set_request)

        if set_result.failed():
            logger.error(
                "Attempted to set workspace project '%s' as current. Failed with: %s",
                workspace_project_path,
                set_result.result_details,
            )
            return

        logger.debug("Successfully loaded workspace project from '%s'", workspace_project_path)

    def _load_registered_projects(self) -> None:
        """Load project templates from paths persisted in user config.

        Called after workspace project loading so that user-registered paths
        are available in the template list. Paths already loaded (e.g., the
        workspace project) are skipped. Missing or invalid files are skipped
        with a warning rather than raising.
        """
        registered_paths: list[str] = self._config_manager.get_config_value(PROJECTS_TO_REGISTER_KEY, default=[]) or []
        for path_str in registered_paths:
            # Project IDs are canonicalized absolute paths, so expand ~/env
            # vars and resolve the persisted string before checking for an
            # existing load (prevents duplicate entries when the same file
            # was persisted under different spellings).
            resolved_id = str(canonicalize_for_identity(path_str))
            if resolved_id in self._successfully_loaded_project_templates:
                continue
            load_request = LoadProjectTemplateRequest(project_path=Path(path_str))
            result = self.on_load_project_template_request(load_request)
            if result.failed():
                logger.warning(
                    "Failed to load registered project '%s' on startup: %s",
                    path_str,
                    result.result_details,
                )
            else:
                logger.info("Reloaded registered project from '%s'", path_str)

    def _register_project_path(self, project_id: str) -> None:
        """Persist a project file path so it is loaded on the next engine restart.

        Appends the path to the projects_to_register config list if not already
        present. Errors are logged as warnings and do not affect the load result.
        """
        try:
            registered: list[str] = self._config_manager.get_config_value(PROJECTS_TO_REGISTER_KEY, default=[]) or []
            # Compare by canonicalized path (~/env expansion + resolution) so a
            # previously persisted relative or ~/ spelling of the same file
            # isn't re-persisted as a duplicate.
            resolved_existing = {str(canonicalize_for_identity(p)) for p in registered}
            if project_id not in resolved_existing:
                self._config_manager.set_config_value(PROJECTS_TO_REGISTER_KEY, [*registered, project_id])
        except Exception:
            logger.warning("Failed to persist project path '%s' to config", project_id)
