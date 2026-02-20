"""ConfigureProjectFileSave node - configure file save paths using macro expansion."""

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
from griptape_nodes.exe_types.param_types.parameter_button import ParameterButton
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.files.file import FileDestination
from griptape_nodes.files.path_utils import parse_filename_components
from griptape_nodes.files.situation_file_builder import SITUATION_TO_FILE_POLICY, fetch_situation_config
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.parameter_events import (
    GetConnectionsForParameterRequest,
    GetConnectionsForParameterResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

_FALLBACK_SITUATIONS = ["save_node_output", "save_file", "copy_external_file", "download_url", "save_preview"]


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


class ConfigureProjectFileSave(BaseNode):
    """Configure file save paths using situation templates and macro expansion.

    Outputs a FileDestination with an unresolved MacroPath so that path resolution
    and write policy are resolved at I/O time.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self._updating_lock = False

        self._available_situations = self._fetch_available_situations()
        self._create_parameters()
        self._load_project_situation()

    def _fetch_available_situations(self) -> list[str]:
        """Fetch available situations from the project manager."""
        request = GetAllSituationsForProjectRequest()
        result = GriptapeNodes.handle_request(request)

        if not isinstance(result, GetAllSituationsForProjectResultSuccess):
            logger.warning("%s: Failed to fetch situations from project", self.name)
            return _FALLBACK_SITUATIONS

        return sorted(result.situations.keys())

    def _create_parameters(self) -> None:
        """Create all parameters for the node."""
        self.situation = ParameterString(
            name="situation",
            default_value="save_node_output",
            allowed_modes={ParameterMode.PROPERTY},
            tooltip="Select the file save situation template to use for path resolution",
            traits={Options(choices=self._available_situations)},
            settable=True,
        )
        self.add_parameter(self.situation)

        with ParameterGroup(name="Situation") as situation_group:
            self.macro = ParameterString(
                name="macro",
                default_value="",
                tooltip="Macro template for output path resolution",
                settable=True,
            )

            self.on_collision = ParameterString(
                name="on_collision",
                default_value=SituationFilePolicy.CREATE_NEW,
                tooltip="Policy for handling existing files when writing",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=[p.value for p in SituationFilePolicy])},
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

        self.absolute_path_warning = ParameterMessage(
            name="absolute_path_warning",
            variant="warning",
            value="The file path specified could not be found within a directory defined within the current project. This may affect portability.",
            ui_options={"hide": True},
        )
        self.add_node_element(self.absolute_path_warning)

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

        self.resolved_path = ParameterString(
            name="resolved_path",
            default_value="",
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Preview of the resolved absolute file path",
        )
        self.add_parameter(self.resolved_path)

        self.file_location = Parameter(
            name="file_location",
            type="FileDestination",
            default_value=None,
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="FileDestination with unresolved macro path and write policy for downstream save nodes",
            output_type="FileDestination",
        )
        self.add_parameter(self.file_location)

    def _load_project_situation(self) -> None:
        """Load situation template from project and set macro default."""
        situation_name = self.get_parameter_value(self.situation.name)
        situation_config = fetch_situation_config(situation_name, self.name)

        self.set_parameter_value(self.macro.name, situation_config.macro_template, initial_setup=True)
        self.set_parameter_value(self.on_collision.name, situation_config.on_collision_value, initial_setup=True)
        self._resolve_and_update_path()

    def _resolve_and_update_path(self) -> None:
        """Resolve the macro and update resolved_path and file_location outputs."""
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
        """Map the current on_collision parameter value to an ExistingFilePolicy."""
        on_collision = self.get_parameter_value(self.on_collision.name) or SituationFilePolicy.CREATE_NEW
        return SITUATION_TO_FILE_POLICY.get(on_collision, ExistingFilePolicy.CREATE_NEW)

    def _build_file_from_template(self, macro_template: str, variables: dict[str, str | int]) -> FileDestination:
        """Build a FileDestination with a MacroPath from a template and variables.

        Args:
            macro_template: The macro template string
            variables: Variable values for macro substitution

        Returns:
            FileDestination with an unresolved MacroPath and baked-in write policy
        """
        macro_path = MacroPath(ParsedMacro(macro_template), variables)
        return FileDestination(macro_path, existing_file_policy=self._get_file_policy())

    def _handle_relative_path(self, classified: ClassifiedPath) -> None:
        """Handle relative path: apply situation template macro."""
        macro_template = self.get_parameter_value(self.macro.name)
        if not macro_template:
            logger.error("%s: No macro template available", self.name)
            return

        filename_path = Path(classified.normalized_path)
        default_ext = parse_filename_components("output.png")[1]
        file_name_base, file_extension = parse_filename_components(filename_path.name, default_extension=default_ext)

        variables: dict[str, str | int] = {
            "file_name_base": file_name_base,
            "file_extension": file_extension,
            "node_name": self._get_target_node_name(),
        }

        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(parsed_macro=parsed_macro, variables=variables)
        )

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        self.set_parameter_value(self.resolved_path.name, str(resolve_result.absolute_path))
        self.set_parameter_value(self.file_location.name, self._build_file_from_template(macro_template, variables))
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_inside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path inside project: use macro form as template."""
        macro_template = classified.normalized_path

        parsed_macro = ParsedMacro(macro_template)
        resolve_result = GriptapeNodes.handle_request(GetPathForMacroRequest(parsed_macro=parsed_macro, variables={}))

        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            logger.error("%s: Failed to resolve macro: %s", self.name, macro_template)
            return

        self.set_parameter_value(self.resolved_path.name, str(resolve_result.absolute_path))
        self.set_parameter_value(self.file_location.name, self._build_file_from_template(macro_template, {}))
        self.absolute_path_warning.ui_options = {"hide": True}

    def _handle_absolute_path_outside_project(self, classified: ClassifiedPath) -> None:
        """Handle absolute path outside project: use directly as a literal path."""
        absolute_path = classified.normalized_path
        self.set_parameter_value(self.resolved_path.name, absolute_path)
        self.set_parameter_value(
            self.file_location.name, FileDestination(absolute_path, existing_file_policy=self._get_file_policy())
        )
        self.absolute_path_warning.ui_options = {"hide": False}

    def _get_target_node_name(self) -> str:
        """Return the name of the downstream node connected to file_location.

        When file_location is connected to a save node, the save node's name is
        used as the node_name macro variable so the output path reflects the
        actual saving node rather than this configuration node.

        Falls back to this node's own name when no connection exists.
        """
        request = GetConnectionsForParameterRequest(parameter_name=self.file_location.name, node_name=self.name)
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, GetConnectionsForParameterResultSuccess) and result.outgoing_connections:
            return result.outgoing_connections[0].target_node_name

        return self.name

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Re-resolve path using the newly connected downstream node's name."""
        if source_parameter.name == self.file_location.name:
            self._resolve_and_update_path()

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Re-resolve path, falling back to this node's own name."""
        if source_parameter.name == self.file_location.name:
            self._resolve_and_update_path()

    def after_value_set(self, parameter: Parameter, value: Any, *, initial_setup: bool = False) -> None:  # noqa: ARG002
        """React to parameter changes by re-resolving the path."""
        if initial_setup or self._updating_lock:
            return

        if parameter.name in (self.situation.name, self.filename.name, self.macro.name, self.on_collision.name):
            self._updating_lock = True
            try:
                if parameter.name == self.situation.name:
                    self._load_project_situation()
                    self.publish_update_to_parameter(self.macro.name, self.get_parameter_value(self.macro.name))
                    self.publish_update_to_parameter(
                        self.on_collision.name, self.get_parameter_value(self.on_collision.name)
                    )
                else:
                    self._resolve_and_update_path()
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
        self.publish_update_to_parameter(self.on_collision.name, self.get_parameter_value(self.on_collision.name))

        return NodeMessageResult(
            success=True,
            details="Situation parameters reset to defaults",
            response=button_details,
            altered_workflow_state=True,
        )
