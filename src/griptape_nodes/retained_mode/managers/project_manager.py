"""ProjectManager - Manages project templates and file save situations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.common.project_templates_stub import (
    DEFAULT_PROJECT_YAML_PATH,
    ProjectTemplate,
    ProjectValidationInfo,
    ProjectValidationStatus,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetCurrentProjectRequest,
    GetCurrentProjectResultSuccess,
    GetMacroForSituationRequest,
    GetMacroForSituationResultFailure,
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    GetProjectTemplateRequest,
    GetProjectTemplateResultFailure,
    GetProjectTemplateResultSuccess,
    LoadProjectTemplateRequest,
    LoadProjectTemplateResultFailure,
    PathResolutionFailureReason,
    SaveProjectTemplateRequest,
    SaveProjectTemplateResultFailure,
    SetCurrentProjectRequest,
    SetCurrentProjectResultSuccess,
)

if TYPE_CHECKING:
    from pathlib import Path

    from griptape_nodes.common.macro_parser import ParsedMacro
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


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

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the ProjectManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        # Track validation status for ALL load attempts (including MISSING/UNUSABLE)
        self.registered_template_status: dict[Path, ProjectValidationInfo] = {}

        # Cache only successfully loaded templates (GOOD or FLAWED)
        self.successful_templates: dict[Path, ProjectTemplate] = {}

        # Cache parsed macros for performance (avoid re-parsing schemas)
        self.parsed_situation_schemas: dict[SituationMacroKey, ParsedMacro] = {}
        self.parsed_directory_schemas: dict[DirectoryMacroKey, ParsedMacro] = {}

        # Track which project.yml user has selected
        self.current_project_path: Path | None = None

        # Load system defaults once at initialization
        self._load_system_defaults()

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

    def _load_system_defaults(self) -> None:
        """Load bundled system default template.

        System defaults MUST be valid (fail-fast if they're not).
        This is called once at initialization.
        """
        # Replace with actual loading logic when template system merges
        # For now, create a minimal stub template
        logger.info("Loading system default template from: %s", DEFAULT_PROJECT_YAML_PATH)

        # Stub implementation - will be replaced with actual file loading
        validation = ProjectValidationInfo(status=ProjectValidationStatus.GOOD)

        # For now, just track that we attempted to load system defaults
        # The actual loading will use ReadFileRequest via OSManager
        self.registered_template_status[DEFAULT_PROJECT_YAML_PATH] = validation

        logger.info("System default template loaded successfully")

    # Event handler methods

    def on_load_project_template_request(self, request: LoadProjectTemplateRequest) -> ResultPayload:
        """Load user's project.yml and merge with system defaults.

        Flow:
        1. Set validation status to MISSING
        2. Issue ReadFileRequest to OSManager
        3. Parse YAML and load partial template (overlay)
        4. Merge with system defaults
        5. Cache in registered_template_status and successful_templates (if usable)
        6. Return success or failure result

        TODO: Implement full loading logic when template system merges
        """
        logger.info("Loading project template: %s", request.project_path)

        # Stub implementation
        validation = ProjectValidationInfo(status=ProjectValidationStatus.MISSING)
        self.registered_template_status[request.project_path] = validation

        return LoadProjectTemplateResultFailure(
            project_path=request.project_path,
            validation=validation,
            result_details="Template loading not yet implemented (stub)",
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

        TODO: Implement when template system merges
        """
        logger.debug("Getting macro for situation: %s in project: %s", request.situation_name, request.project_path)

        return GetMacroForSituationResultFailure(
            result_details="Macro retrieval not yet implemented (stub)",
        )

    def on_get_path_for_macro_request(self, request: GetPathForMacroRequest) -> ResultPayload:
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

        TODO: Implement macro resolution when template system merges
        """
        logger.debug("Resolving macro: %s in project: %s", request.macro_schema, request.project_path)

        return GetPathForMacroResultFailure(
            failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
            error_details="Path resolution not yet implemented (stub)",
            result_details="Path resolution not yet implemented",
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
        logger.info("Saving project template: %s", request.project_path)

        return SaveProjectTemplateResultFailure(
            project_path=request.project_path,
            result_details="Template saving not yet implemented (stub)",
        )
