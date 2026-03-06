"""FileOutputSettings node - configure file save paths using macro expansion."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.exe_types.core_types import (
    NodeMessageResult,
    Parameter,
    ParameterGroup,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import FileDestination
from griptape_nodes.files.path_utils import FilenameParts
from griptape_nodes.files.project_file import FALLBACK_MACRO_TEMPLATE, SITUATION_TO_FILE_POLICY
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

_IF_FILE_EXISTS_CHOICES = [
    {"name": "Increment Version", "option_value": SituationFilePolicy.CREATE_NEW},
    {"name": "Overwrite Existing", "option_value": SituationFilePolicy.OVERWRITE},
    {"name": "Abort / Error", "option_value": SituationFilePolicy.FAIL},
]
_IF_FILE_EXISTS_DISPLAY_NAMES = [choice["name"] for choice in _IF_FILE_EXISTS_CHOICES]
_POLICY_VALUE_TO_DISPLAY_NAME: dict[str, str] = {
    choice["option_value"]: choice["name"] for choice in _IF_FILE_EXISTS_CHOICES
}
_DISPLAY_NAME_TO_POLICY_VALUE: dict[str, str] = {
    choice["name"]: choice["option_value"] for choice in _IF_FILE_EXISTS_CHOICES
}


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


class FileOutputSettings(BaseNode):
    """Configure file save paths using situation templates and macro expansion.

    Stores a FileDestination internally (accessible via the file_destination property)
    and outputs a resolved path string on the file_destination parameter for display.
    Downstream nodes retrieve the FileDestination directly via the FileDestinationProvider
    protocol rather than deserializing it from the wire.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self._updating_lock = False
        self._file_destination: FileDestination | None = None

        self._available_situations = self._fetch_available_situations()
        self._create_parameters()
        self._load_project_situation()

    @property
    def file_destination(self) -> FileDestination | None:
        """The FileDestination built from the current path configuration."""
        return self._file_destination

    def _fetch_available_situations(self) -> list[str]:
        """Fetch available situations from the project manager."""
        request = GetAllSituationsForProjectRequest()
        result = GriptapeNodes.handle_request(request)

        if not isinstance(result, GetAllSituationsForProjectResultSuccess):
            logger.error("%s: Failed to fetch situations from project", self.name)
            return []

        return sorted(result.situations.keys())

    def _create_parameters(self) -> None:
        """Create all parameters for the node."""
        self.situation = ParameterString(
            name="situation",
            default_value=self._available_situations[0],
            allowed_modes={ParameterMode.PROPERTY},
            tooltip="Select the file save situation template to use for path resolution",
            traits={Options(choices=self._available_situations)},
            settable=True,
        )
        self.add_parameter(self.situation)

        with ParameterGroup(name="Situation Options") as situation_group:
            self.macro = ParameterString(
                name="macro",
                default_value="",
                tooltip="Macro template for output path resolution",
                settable=True,
            )

            self.if_file_exists = ParameterString(
                name="if_file_exists",
                default_value=_POLICY_VALUE_TO_DISPLAY_NAME[SituationFilePolicy.CREATE_NEW],
                tooltip="Policy for handling existing files when writing",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=_IF_FILE_EXISTS_DISPLAY_NAMES)},
                settable=True,
            )

            self.auto_create_path = ParameterBool(
                name="auto_create_path",
                default_value=True,
                tooltip="Whether to create parent directories automatically when saving",
                allowed_modes={ParameterMode.PROPERTY},
                settable=True,
            )

            ParameterButton(
                name="reset_situation",
                label="Reset to Default",
                variant="default",
                icon="refresh-cw",
                on_click=self._on_reset_situation_clicked,
            )

        self.add_node_element(situation_group)

        self.absolute_path_warning = ParameterMessage(
            name="absolute_path_warning",
            variant="warning",
            value="The file path specified could not be found within a directory defined within the current project. This will affect portability.",
            ui_options={"hide": True},
        )
        self.add_node_element(self.absolute_path_warning)

        self.filename = ParameterString(
            name="filename",
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

        self.file_destination_parameter = Parameter(
            name="file_destination",
            type="str",
            default_value=None,
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Resolved file path for downstream save nodes",
            output_type="str",
        )
        self.add_parameter(self.file_destination_parameter)

    def _load_project_situation(self) -> None:
        """Load situation template from project and set macro default."""
        situation_name = self.get_parameter_value(self.situation.name)
        result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation_name))

        if isinstance(result, GetSituationResultSuccess):
            macro_template = result.situation.macro
            on_collision = result.situation.policy.on_collision
            create_dirs = result.situation.policy.create_dirs
        else:
            logger.error("%s: Failed to load situation '%s', using fallback macro template", self.name, situation_name)
            macro_template = FALLBACK_MACRO_TEMPLATE
            on_collision = SituationFilePolicy.CREATE_NEW
            create_dirs = True

        self.set_parameter_value(self.macro.name, macro_template, initial_setup=True)
        display_name = _POLICY_VALUE_TO_DISPLAY_NAME.get(
            on_collision, _POLICY_VALUE_TO_DISPLAY_NAME[SituationFilePolicy.CREATE_NEW]
        )
        self.set_parameter_value(self.if_file_exists.name, display_name, initial_setup=True)
        self.set_parameter_value(self.auto_create_path.name, create_dirs, initial_setup=True)
        self._resolve_and_update_path()
        self._update_collision_badge()

    def _resolve_and_update_path(self) -> None:
        """Resolve the macro and update resolved_path and file_destination outputs."""
        file_name_value = self.get_parameter_value(self.filename.name)
        if not file_name_value:
            return

        classified = self._classify_path(file_name_value)

        if isinstance(classified, str):
            return

        if classified.scenario == PathResolutionScenario.RELATIVE_PATH:
            self._handle_relative_path(classified)
        elif classified.scenario == PathResolutionScenario.ABSOLUTE_PATH_INSIDE_PROJECT:
            self._handle_absolute_path_inside_project(classified)
        elif classified.scenario == PathResolutionScenario.ABSOLUTE_PATH_OUTSIDE_PROJECT:
            self._handle_absolute_path_outside_project(classified)

    def _classify_path(self, file_name_value: str) -> ClassifiedPath | str:
        """Classify the user's filename input into one of three scenarios.

        Args:
            file_name_value: The user's input filename/path

        Returns:
            ClassifiedPath with scenario classification, or error message string
        """
        parsed_macro = ParsedMacro(file_name_value)
        parse_result = GriptapeNodes.handle_request(GetPathForMacroRequest(parsed_macro=parsed_macro, variables={}))

        if not isinstance(parse_result, GetPathForMacroResultSuccess):
            return "Failed to parse macro"

        resolved = parse_result.resolved_path

        if not resolved.is_absolute():
            return ClassifiedPath(
                scenario=PathResolutionScenario.RELATIVE_PATH,
                normalized_path=file_name_value,
            )

        map_result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=resolved))

        if isinstance(map_result, AttemptMapAbsolutePathToProjectResultSuccess) and map_result.mapped_path:
            return ClassifiedPath(
                scenario=PathResolutionScenario.ABSOLUTE_PATH_INSIDE_PROJECT,
                normalized_path=map_result.mapped_path,
            )

        return ClassifiedPath(
            scenario=PathResolutionScenario.ABSOLUTE_PATH_OUTSIDE_PROJECT,
            normalized_path=str(resolved),
        )

    def _get_file_policy(self) -> ExistingFilePolicy:
        """Map the current if_file_exists parameter value to an ExistingFilePolicy."""
        display_name = self.get_parameter_value(self.if_file_exists.name)
        policy_value = _DISPLAY_NAME_TO_POLICY_VALUE.get(display_name, SituationFilePolicy.CREATE_NEW)
        return SITUATION_TO_FILE_POLICY.get(policy_value, ExistingFilePolicy.CREATE_NEW)

    def _update_collision_badge(self) -> None:
        """Set or clear the info badge on if_file_exists based on the current policy."""
        display_name = self.get_parameter_value(self.if_file_exists.name)
        policy_value = _DISPLAY_NAME_TO_POLICY_VALUE.get(display_name)
        if policy_value == SituationFilePolicy.CREATE_NEW:
            self.if_file_exists.set_badge(
                variant="info",
                message="Filename is not guaranteed. The next available name will be used if a file already exists.",
            )
        else:
            self.if_file_exists.clear_badge()

    def _build_file_from_template(self, macro_template: str, variables: dict[str, str | int]) -> FileDestination:
        """Build a FileDestination with a MacroPath from a template and variables.

        Args:
            macro_template: The macro template string
            variables: Variable values for macro substitution

        Returns:
            FileDestination with an unresolved MacroPath and baked-in write policy
        """
        macro_path = MacroPath(ParsedMacro(macro_template), variables)
        create_dirs = bool(self.get_parameter_value(self.auto_create_path.name))
        return FileDestination(macro_path, existing_file_policy=self._get_file_policy(), create_parents=create_dirs)

    def _handle_relative_path(self, classified: ClassifiedPath) -> None:
        """Handle relative path: apply situation template macro."""
        macro_template = self.get_parameter_value(self.macro.name)
        if not macro_template:
            logger.error("%s: No macro template available", self.name)
            return

        filename_path = Path(classified.normalized_path)
        parts = FilenameParts.from_filename(filename_path.name)

        variables: dict[str, str | int] = {
            "file_name_base": parts.stem,
            "file_extension": parts.extension,
            "node_name": self._get_target_node_name(),
        }

        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
        )

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        resolved_path_str = str(resolve_result.absolute_path)
        self._file_destination = self._build_file_from_template(macro_template, variables)
        self.set_parameter_value(self.file_destination_parameter.name, resolved_path_str)
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_inside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path inside project: use macro form as template."""
        macro_template = classified.normalized_path

        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.handle_request(GetPathForMacroRequest(parsed_macro=parsed_macro, variables={}))

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        resolved_path_str = str(resolve_result.absolute_path)
        self._file_destination = self._build_file_from_template(macro_template, {})
        self.set_parameter_value(self.file_destination_parameter.name, resolved_path_str)
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_outside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path outside project: use directly as a literal path."""
        absolute_path = classified.normalized_path
        create_dirs = bool(self.get_parameter_value(self.auto_create_path.name))
        self._file_destination = FileDestination(
            absolute_path,
            existing_file_policy=self._get_file_policy(),
            create_parents=create_dirs,
        )
        self.set_parameter_value(self.file_destination_parameter.name, absolute_path)
        self.absolute_path_warning.ui_options = {"hide": False}

    def _get_target_node_name(self) -> str:
        """Return the name of the downstream node connected to file_destination.

        When file_destination is connected to a save node, the save node's name is
        used as the node_name macro variable so the output path reflects the
        actual saving node rather than this configuration node.

        Falls back to this node's own name when no connection exists.
        """
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name))
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            for conn in result.outgoing_connections:
                if conn.source_parameter_name == self.file_destination_parameter.name:
                    return conn.target_node_name
        return self.name

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Re-resolve path using the newly connected downstream node's name."""
        if source_parameter.name == self.file_destination_parameter.name:
            self._resolve_and_update_path()

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Re-resolve path, falling back to this node's own name."""
        if source_parameter.name == self.file_destination_parameter.name:
            self._resolve_and_update_path()

    def after_value_set(self, parameter: Parameter, value: Any, *, initial_setup: bool = False) -> None:  # noqa: ARG002
        """React to parameter changes by re-resolving the path."""
        if initial_setup or self._updating_lock:
            return

        if parameter.name in (
            self.situation.name,
            self.filename.name,
            self.macro.name,
            self.if_file_exists.name,
            self.auto_create_path.name,
        ):
            self._updating_lock = True
            try:
                if parameter.name == self.situation.name:
                    self._load_project_situation()
                    self.publish_update_to_parameter(self.macro.name, self.get_parameter_value(self.macro.name))
                    self.publish_update_to_parameter(
                        self.if_file_exists.name, self.get_parameter_value(self.if_file_exists.name)
                    )
                else:
                    self._resolve_and_update_path()
                    if parameter.name == self.if_file_exists.name:
                        self._update_collision_badge()
            finally:
                self._updating_lock = False

    def process(self) -> None:
        """Resolve the path and set output parameter values."""
        self._resolve_and_update_path()

    def _on_reset_situation_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Reset macro to the situation's default template."""
        self._load_project_situation()

        self.publish_update_to_parameter(self.macro.name, self.get_parameter_value(self.macro.name))
        self.publish_update_to_parameter(self.if_file_exists.name, self.get_parameter_value(self.if_file_exists.name))
        self.publish_update_to_parameter(
            self.auto_create_path.name, self.get_parameter_value(self.auto_create_path.name)
        )

        return NodeMessageResult(
            success=True,
            details="Situation parameters reset to defaults",
            response=button_details,
            altered_workflow_state=True,
        )
