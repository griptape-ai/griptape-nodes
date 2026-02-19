from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class FileSelector(DataNode):
    """Select a file and resolve it to a macro path using project situations."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.selected_file_input = ParameterString(
            name="selected_file",
            default_value="",
            tooltip="The file to select.",
            allow_output=False,
        )
        self.selected_file_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
            )
        )
        self.add_parameter(self.selected_file_input)

        self.add_parameter(
            ParameterString(
                name="macro_path",
                allow_input=False,
                allow_output=False,
                allow_property=False,
                default_value="",
                tooltip="The matched macro path string, or the raw file path if no situation matched.",
            )
        )

        self.add_parameter(
            ParameterString(
                name="file_path",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The resolved file path or macro path for downstream nodes.",
                hide_property=True,
            )
        )

    def _resolve_macro_path(self, file_path_str: str) -> str:
        """Attempt to map the file path to a directory-level macro path.

        Returns the macro form (e.g., {outputs}/file.png) if the path is inside a
        project directory, or the raw file path string as fallback.
        """
        if not file_path_str:
            return ""

        result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=Path(file_path_str)))

        if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
            return result.mapped_path

        return file_path_str

    def _update_macro_path(self, file_path_str: str) -> None:
        """Compute the macro path and publish it as the file_path output value.

        Downstream nodes connected to file_path receive the macro path.
        The macro_path parameter is updated for display only (readonly, no output).
        """
        macro_path = self._resolve_macro_path(file_path_str)
        self.parameter_output_values["file_path"] = macro_path
        self.publish_update_to_parameter("file_path", macro_path)
        self.parameter_output_values["macro_path"] = macro_path
        self.publish_update_to_parameter("macro_path", macro_path)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "selected_file":
            if value is not None:
                file_path_str = str(value)
            else:
                file_path_str = ""
            self._update_macro_path(file_path_str)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        file_path_str = self.get_parameter_value("selected_file")
        if file_path_str is not None:
            file_path_str = str(file_path_str)
        else:
            file_path_str = ""
        self._update_macro_path(file_path_str)
