"""ResolveFilePath Node - Standalone path resolution with macro expansion.

This node handles:
- Project template macro resolution
- Path classification (relative/absolute inside/outside project)
- UI management (buttons, warnings, info messages)
- Output: fully resolved file path ready for use by save nodes
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates import SituationFilePolicy
from griptape_nodes.exe_types.core_types import (
    NodeMessageResult,
    Parameter,
    ParameterGroup,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.project import ExistingFilePolicy, ProjectFileConfig
from griptape_nodes.retained_mode.events.os_events import (
    DryRunWriteFileRequest,
    WriteFileResultDryRun,
)
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy as OSExistingFilePolicy,
)
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")


# String constants for file policy UI strings
POLICY_STRING_CREATE_NEW = "create new file"
POLICY_STRING_OVERWRITE = "overwrite existing file"
POLICY_STRING_FAIL = "fail if file exists"


class PathResolutionScenario(StrEnum):
    """Classification of how to handle user's filename input."""

    RELATIVE_PATH = "relative_path"
    ABSOLUTE_PATH_INSIDE_PROJECT = "absolute_path_inside_project"
    ABSOLUTE_PATH_OUTSIDE_PROJECT = "absolute_path_outside_project"


@dataclass
class ClassifiedPath:
    """Result of classifying user's filename input.

    Attributes:
        scenario: Which scenario this input represents
        normalized_path: The path after macro resolution
        macro_form: For ABSOLUTE_PATH_INSIDE_PROJECT, the macro form of the path
    """

    scenario: PathResolutionScenario
    normalized_path: str
    macro_form: str | None = None


class ResolveFilePath(BaseNode):
    """Node for resolving file paths with macro expansion and project template integration.

    This node handles path resolution and outputs a fully resolved path string.
    Save nodes can use this output to determine where to save files.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self._updating_lock = False

        # Fetch available situations from project
        self._available_situations = self._fetch_available_situations()

        # Create parameters
        self._create_parameters()

        # Load project situation and perform initial resolution
        self._load_project_situation()

    def _fetch_available_situations(self) -> list[str]:
        """Fetch available situations from ProjectManager.

        Returns:
            List of situation names, or fallback list if fetch fails
        """
        request = GetAllSituationsForProjectRequest()
        result = GriptapeNodes.ProjectManager().on_get_all_situations_for_project_request(request)

        if not isinstance(result, GetAllSituationsForProjectResultSuccess):
            logger.warning("%s: Failed to fetch situations from project", self.name)
            # Fallback to known default situations
            return ["save_node_output", "save_file", "copy_external_file", "download_url", "save_preview"]

        return sorted(result.situations.keys())

    def _create_parameters(self) -> None:
        """Create all parameters for the node."""
        # situation parameter (dropdown selector)
        self.situation = ParameterString(
            name="situation",
            default_value="save_node_output",
            allowed_modes={ParameterMode.PROPERTY},
            tooltip="Select the file save situation template to use for path resolution",
            traits={Options(choices=self._available_situations)},
            settable=True,
        )
        self.add_parameter(self.situation)

        # Situation group
        with ParameterGroup(name="Situation") as situation_group:
            self.macro = ParameterString(
                name="macro",
                default_value="",
                tooltip="Macro template for output path resolution",
                settable=True,
            )

            self.allow_creating_intermediate_dirs = Parameter(
                name="allow_creating_intermediate_dirs",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Allow creating parent directories if they don't exist",
                settable=True,
            )

            self.overwrite_policy = Parameter(
                name="overwrite_policy",
                type="str",
                default_value=POLICY_STRING_CREATE_NEW,
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Policy for handling existing files",
                traits={
                    Options(choices=[POLICY_STRING_CREATE_NEW, POLICY_STRING_OVERWRITE, POLICY_STRING_FAIL]),
                },
                settable=True,
            )

            ParameterButton(
                name="reset_situation",
                label="Reset",
                variant="default",
                icon="refresh-cw",
                on_click=self._on_reset_situation_clicked,
            )

        self.add_node_element(situation_group)

        # Absolute path warning
        self.absolute_path_warning = ParameterMessage(
            name="absolute_path_warning",
            variant="warning",
            value="The file path specified could not be found within a directory defined within the current project. This may affect portability.",
            ui_options={"hide": True},
        )
        self.add_node_element(self.absolute_path_warning)

        # filename parameter (user input)
        self.filename = ParameterString(
            name="filename",
            default_value="output.png",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="Filename with extension (supports macros like {workflow_name}_output.png)",
            traits={
                FileSystemPicker(
                    allow_files=True,
                    allow_directories=False,
                    allow_create=True,
                    workspace_only=False,
                )
            },
        )
        self.add_parameter(self.filename)

        # resolved_path parameter (computed output)
        self.resolved_path = ParameterString(
            name="resolved_path",
            default_value="",
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Final resolved output path",
        )
        self.add_parameter(self.resolved_path)

        # Preview button and result message
        self.preview_write_button = ParameterButton(
            name="preview_write",
            label="Preview Write",
            variant="secondary",
            icon="eye",
            on_click=self._on_preview_write_clicked,
        )
        self.add_node_element(self.preview_write_button)

        self.preview_result = ParameterMessage(
            name="preview_result",
            variant="info",
            value="",
            ui_options={"hide": True},
        )
        self.add_node_element(self.preview_result)

        # file_location parameter (computed output with policies)
        # This is an OUTPUT-only parameter that produces ProjectFileConfig objects
        # It doesn't need ProjectFileConfigParameter component since it never calls save/load
        def _normalize_file_location(value: Any) -> Any:
            """Normalize ProjectFileConfig values for output."""
            if value is None:
                return None
            if isinstance(value, ProjectFileConfig):
                return value
            if isinstance(value, dict):
                return ProjectFileConfig(**value)
            return value

        self.file_location = Parameter(
            name="file_location",
            type="ProjectFileConfig",
            input_types=["ProjectFileConfig"],
            output_type="ProjectFileConfig",
            default_value=None,
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Complete file location with path and save policies",
            converters=[_normalize_file_location],
        )
        self.add_parameter(self.file_location)

    def set_parameter_value(self, param_name: str, value: Any, **kwargs: Any) -> None:
        """Override to handle reactive path resolution updates."""
        super().set_parameter_value(param_name, value, **kwargs)

        # Skip during initial setup
        if kwargs.get("initial_setup"):
            return

        # Skip if we're already in a sync operation
        if self._updating_lock:
            return

        # Check if this is a parameter we manage
        managed_params = {
            self.situation.name,
            self.filename.name,
            self.macro.name,
            self.allow_creating_intermediate_dirs.name,
            self.overwrite_policy.name,
        }

        if param_name not in managed_params:
            return

        # Acquire lock - this parameter is triggering the atomic sync
        self._updating_lock = True
        try:
            # Handle parameter changes
            if param_name == self.situation.name:
                # Situation changes reload the entire template
                self._load_project_situation()
            else:
                # Other parameter changes trigger path resolution
                self._resolve_and_update_path()
        finally:
            # Always clear the lock
            self._updating_lock = False

    def process(self) -> None:
        """Process method - resolves path and outputs result."""
        filename_value = self.get_parameter_value("filename")

        if not filename_value:
            error_msg = "No filename provided"
            raise ValueError(error_msg)

        # Resolve path
        self._resolve_and_update_path()

        # The resolved path is already set in output by _resolve_and_update_path

    # Private methods for situation loading and path resolution

    def _get_target_node_name(self) -> str:
        """Get the name of the node this ResolveFilePath is connected to.

        If file_location output has outgoing connections, use the first target node's name.
        Otherwise, fall back to this node's own name.

        Returns:
            Target node name if connected, otherwise this node's name
        """
        from griptape_nodes.retained_mode.events.parameter_events import (
            GetConnectionsForParameterRequest,
            GetConnectionsForParameterResultSuccess,
        )

        request = GetConnectionsForParameterRequest(parameter_name=self.file_location.name, node_name=self.name)
        result = GriptapeNodes.NodeManager().on_get_connections_for_parameter_request(request)

        if isinstance(result, GetConnectionsForParameterResultSuccess) and result.outgoing_connections:
            # Use the first target node's name
            return result.outgoing_connections[0].target_node_name

        # Fallback to this node's name
        return self.name

    def after_outgoing_connection(
        self, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter
    ) -> None:
        """Callback after a connection FROM this node was created.

        Re-resolve the path to use the target node's name.
        """
        if source_parameter.name == self.file_location.name:
            # Re-compute the ProjectFileConfig with the target node's name
            self._resolve_and_update_path()

        return super().after_outgoing_connection(source_parameter, target_node, target_parameter)

    def after_outgoing_connection_removed(
        self, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter
    ) -> None:
        """Callback after a connection FROM this node was removed.

        Re-resolve the path to use this node's own name.
        """
        if source_parameter.name == self.file_location.name:
            # Re-compute the ProjectFileConfig with this node's own name
            self._resolve_and_update_path()

        return super().after_outgoing_connection_removed(source_parameter, target_node, target_parameter)

    def _load_project_situation(self) -> None:
        """Load situation template from ProjectManager and set defaults."""
        situation_name = self.get_parameter_value(self.situation.name)
        request = GetSituationRequest(situation_name=situation_name)
        result = GriptapeNodes.ProjectManager().on_get_situation_request(request)

        if not isinstance(result, GetSituationResultSuccess):
            logger.warning("%s: Could not load situation template '%s'", self.name, situation_name)
            return

        # Set macro parameter value
        self.set_parameter_value(self.macro.name, result.situation.macro, initial_setup=True)

        # Set policy defaults
        self.set_parameter_value(
            self.allow_creating_intermediate_dirs.name,
            result.situation.policy.create_dirs,
            initial_setup=True,
        )

        # Convert enum to UI string for overwrite_policy
        policy_ui_string = self._policy_to_ui_string(result.situation.policy.on_collision)
        self.set_parameter_value(
            self.overwrite_policy.name,
            policy_ui_string,
            initial_setup=True,
        )

        # Initial path resolution
        self._resolve_and_update_path()

    def _resolve_and_update_path(self) -> None:
        """Resolve macro and update resolved_path."""
        file_name_value = self.get_parameter_value(self.filename.name)
        if not file_name_value:
            return

        # Classify the path
        classified = self._classify_path(file_name_value)

        if isinstance(classified, str):
            # Error during classification
            return

        # Handle based on scenario
        if classified.scenario == PathResolutionScenario.RELATIVE_PATH:
            self._handle_relative_path(classified)
        elif classified.scenario == PathResolutionScenario.ABSOLUTE_PATH_INSIDE_PROJECT:
            self._handle_absolute_path_inside_project(classified)
        elif classified.scenario == PathResolutionScenario.ABSOLUTE_PATH_OUTSIDE_PROJECT:
            self._handle_absolute_path_outside_project(classified)

    def _classify_path(self, file_name_value: str) -> ClassifiedPath | str:
        """Classify path into one of three scenarios.

        Args:
            file_name_value: The user's input filename/path

        Returns:
            ClassifiedPath with scenario, or error message string
        """
        # First, resolve any macros in the input
        parsed_macro = ParsedMacro(file_name_value)
        parse_result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(
            GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})
        )

        if not isinstance(parse_result, GetPathForMacroResultSuccess):
            return "Failed to parse macro"

        resolved = parse_result.resolved_path

        # Check if absolute
        if not resolved.is_absolute():
            return ClassifiedPath(
                scenario=PathResolutionScenario.RELATIVE_PATH,
                normalized_path=file_name_value,
            )

        # Try to map to project directory
        map_result = GriptapeNodes.ProjectManager().on_attempt_map_absolute_path_to_project_request(
            AttemptMapAbsolutePathToProjectRequest(absolute_path=resolved)
        )

        if isinstance(map_result, AttemptMapAbsolutePathToProjectResultSuccess) and map_result.mapped_path:
            return ClassifiedPath(
                scenario=PathResolutionScenario.ABSOLUTE_PATH_INSIDE_PROJECT,
                normalized_path=map_result.mapped_path,
            )

        return ClassifiedPath(
            scenario=PathResolutionScenario.ABSOLUTE_PATH_OUTSIDE_PROJECT,
            normalized_path=str(resolved),
        )

    def _create_file_location(self, macro_template: str, _variables: dict[str, str | int]) -> ProjectFileConfig:
        """Create ProjectFileConfig from macro template, variables, and current policies.

        Args:
            macro_template: The macro template string
            variables: Variables for macro resolution

        Returns:
            ProjectFileConfig object with template, variables, and configured policies
        """
        overwrite_policy_ui = self.get_parameter_value(self.overwrite_policy.name)
        allow_create_dirs = self.get_parameter_value(self.allow_creating_intermediate_dirs.name)
        existing_file_policy = self._ui_string_to_policy(overwrite_policy_ui)

        return ProjectFileConfig(
            macro_template=macro_template,
            policy=existing_file_policy,
            create_dirs=allow_create_dirs,
        )

    def _handle_relative_path(self, classified: ClassifiedPath) -> None:
        """Handle relative path - apply situation template macro."""
        logger.debug("%s: Handling relative path: %s", self.name, classified.normalized_path)

        # Get the macro template
        macro_template = self.get_parameter_value(self.macro.name)
        if not macro_template:
            logger.error("%s: No macro template available", self.name)
            return

        # Parse the filename to extract variables
        from pathlib import Path

        filename_path = Path(classified.normalized_path)

        # Extract file parts
        file_name_base = filename_path.stem
        file_extension = filename_path.suffix.lstrip(".")

        # Build variable dict - use target node name if connected, otherwise use own name
        variables: dict[str, str | int] = {
            "file_name_base": file_name_base,
            "file_extension": file_extension,
            "node_name": self._get_target_node_name(),
        }

        # Resolve the macro to get the absolute path for display in resolved_path output
        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(
            GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
        )

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        # Set resolved_path output for display
        resolved_absolute_path = str(resolve_result.absolute_path)
        self.set_parameter_value(self.resolved_path.name, resolved_absolute_path)

        # Create and set file_location output with template and variables
        file_location = self._create_file_location(macro_template, variables)
        self.set_parameter_value(self.file_location.name, file_location)

        # Hide warning
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_inside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path inside project - use macro form as template."""
        logger.debug("%s: Handling absolute path inside project: %s", self.name, classified.normalized_path)

        # The normalized_path is in macro form (e.g., "{outputs}/file.png")
        macro_template = classified.normalized_path

        # Resolve it to get the absolute path for display
        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(
            GetPathForMacroRequest(parsed_macro=parsed_macro, variables={})
        )

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        # Set resolved_path output for display
        resolved_absolute_path = str(resolve_result.absolute_path)
        self.set_parameter_value(self.resolved_path.name, resolved_absolute_path)

        # Create and set file_location output with macro template and empty variables
        file_location = self._create_file_location(macro_template, {})
        self.set_parameter_value(self.file_location.name, file_location)

        # Hide warning
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_outside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path outside project - use directly as literal template, show warning."""
        logger.debug("%s: Handling absolute path outside project: %s", self.name, classified.normalized_path)

        # Use the absolute path directly
        absolute_path = classified.normalized_path
        self.set_parameter_value(self.resolved_path.name, absolute_path)

        # Create file_location with the absolute path as a literal template (no variables)
        file_location = self._create_file_location(absolute_path, {})
        self.set_parameter_value(self.file_location.name, file_location)

        # Show absolute path warning
        self.absolute_path_warning.ui_options = {"hide": False}

    # Private methods for button handlers

    def _on_reset_situation_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Handle Reset to Situation Defaults button click."""
        self._load_project_situation()

        # Publish updates to UI
        self.publish_update_to_parameter(self.macro.name, self.get_parameter_value(self.macro.name))
        self.publish_update_to_parameter(
            self.allow_creating_intermediate_dirs.name,
            self.get_parameter_value(self.allow_creating_intermediate_dirs.name),
        )
        self.publish_update_to_parameter(
            self.overwrite_policy.name, self.get_parameter_value(self.overwrite_policy.name)
        )

        return NodeMessageResult(
            success=True,
            details="Situation parameters reset to defaults",
            response=button_details,
            altered_workflow_state=True,
        )

    def _on_preview_write_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Handle Preview Write button click - shows what would happen during a write operation."""
        resolved_path = self.get_parameter_value(self.resolved_path.name)

        if not resolved_path:
            self.preview_result.variant = "error"
            self.preview_result.value = "No resolved path available. Please provide a filename."
            self.preview_result.ui_options = {"hide": False}

            return NodeMessageResult(
                success=False,
                details="No resolved path available",
                response=button_details,
                altered_workflow_state=False,
            )

        # Get current policy settings
        overwrite_policy_ui = self.get_parameter_value(self.overwrite_policy.name)
        allow_create_dirs = self.get_parameter_value(self.allow_creating_intermediate_dirs.name)
        existing_file_policy = self._ui_string_to_policy(overwrite_policy_ui)

        # Convert to OS-level policy for DryRunWriteFileRequest
        os_policy_mapping = {
            ExistingFilePolicy.CREATE_NEW: OSExistingFilePolicy.CREATE_NEW,
            ExistingFilePolicy.OVERWRITE: OSExistingFilePolicy.OVERWRITE,
            ExistingFilePolicy.FAIL: OSExistingFilePolicy.FAIL,
        }
        os_existing_file_policy = os_policy_mapping[existing_file_policy]

        # Create dry-run request with test content
        request = DryRunWriteFileRequest(
            file_path=resolved_path,
            content=b"test content",
            existing_file_policy=os_existing_file_policy,
            create_parents=allow_create_dirs,
        )

        # Execute dry-run
        result = GriptapeNodes.OSManager().on_dry_run_write_file_request(request)

        if not isinstance(result, WriteFileResultDryRun):
            self.preview_result.variant = "error"
            self.preview_result.value = "Dry-run failed unexpectedly"
            self.preview_result.ui_options = {"hide": False}

            return NodeMessageResult(
                success=False,
                details="Dry-run failed",
                response=button_details,
                altered_workflow_state=False,
            )

        # Display result
        details_str = str(result.result_details)
        if result.would_succeed:
            self.preview_result.variant = "success"
            self.preview_result.value = f"✓ {details_str}"
        else:
            self.preview_result.variant = "warning"
            self.preview_result.value = f"⚠ {details_str}"

        self.preview_result.ui_options = {"hide": False}

        return NodeMessageResult(
            success=True,
            details=details_str,
            response=button_details,
            altered_workflow_state=False,
        )

    # Private methods for policy conversion

    def _policy_to_ui_string(self, policy: SituationFilePolicy) -> str:
        """Convert SituationFilePolicy enum to UI string."""
        mapping = {
            SituationFilePolicy.CREATE_NEW: POLICY_STRING_CREATE_NEW,
            SituationFilePolicy.OVERWRITE: POLICY_STRING_OVERWRITE,
            SituationFilePolicy.FAIL: POLICY_STRING_FAIL,
        }
        return mapping.get(policy, POLICY_STRING_CREATE_NEW)

    def _ui_string_to_policy(self, ui_string: str) -> ExistingFilePolicy:
        """Convert UI string to ExistingFilePolicy enum."""
        mapping = {
            POLICY_STRING_CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
            POLICY_STRING_OVERWRITE: ExistingFilePolicy.OVERWRITE,
            POLICY_STRING_FAIL: ExistingFilePolicy.FAIL,
        }
        return mapping.get(ui_string, ExistingFilePolicy.OVERWRITE)
