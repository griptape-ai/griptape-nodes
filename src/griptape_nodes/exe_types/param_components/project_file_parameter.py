"""ProjectFileParameter - parameter component for project-aware file saving."""

import logging

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy
from griptape_nodes.exe_types.core_types import NodeMessageResult, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.files.file import File
from griptape_nodes.files.path_utils import parse_filename_components
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterResultSuccess
from griptape_nodes.retained_mode.events.project_events import (
    GetSituationRequest,
    GetSituationResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.retained_mode import RetainedMode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.file_system_picker import FileSystemPicker

logger = logging.getLogger("griptape_nodes")

_FALLBACK_MACRO_TEMPLATE = "{outputs}/{node_name?:_}{file_name_base}{_index?:03}.{file_extension}"

_SITUATION_TO_FILE_POLICY: dict[str, ExistingFilePolicy] = {
    SituationFilePolicy.CREATE_NEW: ExistingFilePolicy.CREATE_NEW,
    SituationFilePolicy.OVERWRITE: ExistingFilePolicy.OVERWRITE,
    SituationFilePolicy.FAIL: ExistingFilePolicy.FAIL,
    SituationFilePolicy.PROMPT: ExistingFilePolicy.CREATE_NEW,  # PROMPT has no direct mapping; fall back to CREATE_NEW
}


class ProjectFileParameter:
    """Parameter component for project-aware file saving.

    Adds a file path parameter to a node that, when processed, returns a
    File object containing a MacroPath for deferred path resolution.

    Usage:
        # In node __init__:
        self._file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="image.png",
        )
        self._file_param.add_parameter()

        # In node process():
        output_file = self._file_param.build_file(sub_dirs="renders")
    """

    def __init__(
        self,
        node: BaseNode,
        name: str,
        situation: str,
        *,
        default_filename: str = "output.png",
        allowed_modes: set[ParameterMode] | None = None,
    ) -> None:
        """Initialize with situation context.

        Args:
            node: Parent node instance
            name: Parameter name
            situation: Situation name (e.g., "save_node_output")
            default_filename: Default filename if parameter is empty
            allowed_modes: Set of allowed parameter modes (default: INPUT, PROPERTY)
        """
        self._node = node
        self._name = name
        self._situation_name = situation
        self._default_filename = default_filename
        self._allowed_modes = allowed_modes or {ParameterMode.INPUT, ParameterMode.PROPERTY}

        # Fetch situation's macro template and policy directly via GetSituationRequest
        get_situation_result = GriptapeNodes.handle_request(GetSituationRequest(situation_name=situation))

        if isinstance(get_situation_result, GetSituationResultSuccess):
            self._macro_template = get_situation_result.situation.macro
            self._existing_file_policy = _SITUATION_TO_FILE_POLICY.get(
                get_situation_result.situation.policy.on_collision,
                ExistingFilePolicy.CREATE_NEW,
            )
        else:
            logger.error(
                "%s: Failed to load situation '%s', using fallback macro template",
                self._node.name,
                situation,
            )
            self._macro_template = _FALLBACK_MACRO_TEMPLATE
            self._existing_file_policy = ExistingFilePolicy.CREATE_NEW

    def add_parameter(self) -> None:
        """Create and add the file path parameter to the node."""
        from griptape_nodes.exe_types.core_types import Parameter

        tooltip = f"Output filename (uses '{self._situation_name}' situation template)"

        traits: set = {
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
                allow_create=True,
            )
        }

        if ParameterMode.INPUT in self._allowed_modes:
            traits.add(
                Button(
                    icon="cog",
                    size="icon",
                    variant="secondary",
                    tooltip="Create and connect a ConfigureProjectFileSave node",
                    on_click=self._on_configure_button_clicked,
                )
            )

        parameter = Parameter(
            name=self._name,
            type="str",
            default_value=self._default_filename,
            allowed_modes=self._allowed_modes,
            tooltip=tooltip,
            input_types=["File", "str"],
            output_type="File",
            traits=traits,
        )

        self._node.add_parameter(parameter)

    def build_file(self, **extra_vars: str | int) -> File:
        """Build a File with a MacroPath from the parameter's current value.

        If the parameter already holds a File (e.g., passed from a
        ConfigureProjectFileSave node), returns it as-is.

        If the parameter holds a string filename, parses it into
        file_name_base/file_extension, builds a MacroPath using the
        situation's macro template, and wraps it in a File.

        Args:
            **extra_vars: Additional variables for the macro (e.g., sub_dirs="renders")

        Returns:
            File object with a MacroPath for deferred path resolution
        """
        value = self._node.get_parameter_value(self._name)

        if isinstance(value, File):
            return value

        if isinstance(value, str) and value:
            filename = value
        else:
            filename = self._default_filename

        default_extension = parse_filename_components(self._default_filename)[1]
        file_name_base, file_extension = parse_filename_components(filename, default_extension=default_extension)

        variables: dict[str, str | int] = {
            "file_name_base": file_name_base,
            "file_extension": file_extension,
            "node_name": self._node.name,
            **extra_vars,
        }

        macro_path = MacroPath(ParsedMacro(self._macro_template), variables)
        return File(macro_path, existing_file_policy=self._existing_file_policy)

    def _on_configure_button_clicked(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Create and connect a ConfigureProjectFileSave node to this parameter."""
        node_name = self._node.name

        connections_result = RetainedMode.get_connections_for_parameter(parameter_name=self._name, node_name=node_name)

        if (
            isinstance(connections_result, GetConnectionsForParameterResultSuccess)
            and connections_result.has_incoming_connections()
        ):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: {self._name} parameter already has an incoming connection",
                response=button_details,
                altered_workflow_state=False,
            )

        create_result = RetainedMode.create_node_relative_to(
            reference_node_name=node_name,
            new_node_type="ConfigureProjectFileSave",
            offset_side="left",
            offset_x=-750,
            offset_y=0,
            lock=False,
        )

        if not isinstance(create_result, str):
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to create ConfigureProjectFileSave node",
                response=button_details,
                altered_workflow_state=False,
            )

        configure_node_name = create_result

        connection_result = RetainedMode.connect(
            source=f"{configure_node_name}.file_location",
            destination=f"{node_name}.{self._name}",
        )

        if not connection_result.succeeded():
            return NodeMessageResult(
                success=False,
                details=f"{node_name}: Failed to connect {configure_node_name}.file_location to {self._name}",
                response=button_details,
                altered_workflow_state=True,
            )

        return NodeMessageResult(
            success=True,
            details=f"{node_name}: Created and connected {configure_node_name}",
            response=button_details,
            altered_workflow_state=True,
        )
