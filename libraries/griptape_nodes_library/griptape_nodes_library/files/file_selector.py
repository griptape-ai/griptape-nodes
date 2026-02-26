from pathlib import Path
from typing import Any

from griptape.artifacts import UrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
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
        self._resolving_macro_path = False

        self.selected_file_input = ParameterString(
            name="selected_file",
            default_value="",
            tooltip="The file to select.",
        )
        self.selected_file_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
            )
        )
        self.add_parameter(self.selected_file_input)

        self.add_parameter(
            Parameter(
                name="url",
                type="UrlArtifact",
                default_value=None,
                tooltip="The resolved file path as a URL artifact.",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _resolve_macro_path(self, file_path_str: str) -> str | None:
        """Attempt to map the file path to a directory-level macro path.

        Returns the macro form (e.g., {outputs}/file.png) if the path is inside a
        project directory, or None if the path is not absolute or no match was found.
        """
        if not file_path_str:
            return None

        result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=Path(file_path_str)))

        if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
            return result.mapped_path

        return None

    def _update_macro_path(self, file_path_str: str) -> None:
        """Resolve the file path to a macro path and assign the result to both selected_file and url.

        Uses the macro path if one is found, otherwise falls back to the raw path.
        """
        macro_path = self._resolve_macro_path(file_path_str)
        output_path = macro_path if macro_path is not None else file_path_str
        url_value = UrlArtifact(output_path) if output_path else None
        self.set_parameter_value("selected_file", output_path)
        self.parameter_output_values["url"] = url_value
        self.publish_update_to_parameter("url", url_value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "selected_file" and not self._resolving_macro_path:
            self._resolving_macro_path = True
            try:
                file_path_str = str(value) if value is not None else ""
                self._update_macro_path(file_path_str)
            finally:
                self._resolving_macro_path = False

        return super().after_value_set(parameter, value)

