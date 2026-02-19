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
    """Select a file and resolve it to a macro path using project directories."""

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
        )
        self.selected_file_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=True,
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "selected_file":
            file_path_str = str(value) if value is not None else ""
            self._update_url_output(file_path_str)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        file_path_str = self.get_parameter_value("selected_file") or ""
        self._update_url_output(str(file_path_str))

    def _resolve_url(self, file_path_str: str) -> UrlArtifact | None:
        """Resolve a file path to a UrlArtifact, mapping to a macro path if one exists."""
        if not file_path_str:
            return None

        result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=Path(file_path_str)))

        if isinstance(result, AttemptMapAbsolutePathToProjectResultSuccess) and result.mapped_path is not None:
            return UrlArtifact(result.mapped_path)

        return UrlArtifact(file_path_str)

    def _update_url_output(self, file_path_str: str) -> None:
        """Compute the URL output from the given file path and keep both parameters in sync."""
        url_value = self._resolve_url(file_path_str)
        mapped_path = url_value.value if url_value is not None else ""

        # Direct assignment bypasses hooks to avoid re-triggering after_value_set
        self.parameter_values["selected_file"] = mapped_path
        self.publish_update_to_parameter("selected_file", mapped_path)

        self.parameter_output_values["url"] = url_value
        self.publish_update_to_parameter("url", url_value)
