from pathlib import Path
from typing import Any

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMatchPathAgainstMacroRequest,
    AttemptMatchPathAgainstMacroResultSuccess,
    GetAllSituationsForProjectRequest,
    GetAllSituationsForProjectResultSuccess,
    GetCurrentProjectRequest,
    GetCurrentProjectResultSuccess,
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

        self.file_path_input = ParameterString(
            name="file_path",
            default_value="",
            tooltip="The file to select.",
        )
        self.file_path_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=False,
            )
        )
        self.add_parameter(self.file_path_input)

        self.add_parameter(
            ParameterString(
                name="macro_path",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The matched macro path string, or the raw file path if no situation matched.",
            )
        )

    def _resolve_macro_path(self, file_path_str: str) -> str:
        """Attempt to match the file path against project situation macros.

        Returns the matched situation macro template string if a situation matches,
        or the raw file path string if no situation matched.
        """
        if not file_path_str:
            return ""

        # Get the current project to obtain project_base_dir
        project_result = GriptapeNodes.handle_request(GetCurrentProjectRequest())
        if not isinstance(project_result, GetCurrentProjectResultSuccess):
            return file_path_str

        project_base_dir = project_result.project_info.project_base_dir

        # Make the path relative to the project base directory
        try:
            relative_path_str = str(Path(file_path_str).relative_to(project_base_dir))
        except ValueError:
            return file_path_str

        # Get all situations for the current project
        situations_result = GriptapeNodes.handle_request(GetAllSituationsForProjectRequest())
        if not isinstance(situations_result, GetAllSituationsForProjectResultSuccess):
            return file_path_str

        # Try to match the relative path against each situation macro
        for macro_string in situations_result.situations.values():
            try:
                parsed = ParsedMacro(macro_string)
            except MacroSyntaxError:
                continue

            match_result = GriptapeNodes.handle_request(
                AttemptMatchPathAgainstMacroRequest(
                    parsed_macro=parsed,
                    file_path=relative_path_str,
                    known_variables={},
                )
            )

            if (
                isinstance(match_result, AttemptMatchPathAgainstMacroResultSuccess)
                and match_result.match_failure is None
            ):
                return parsed.template

        return file_path_str

    def _update_macro_path(self, file_path_str: str) -> None:
        """Compute and publish the macro_path output parameter."""
        macro_path = self._resolve_macro_path(file_path_str)
        self.parameter_output_values["macro_path"] = macro_path
        self.publish_update_to_parameter("macro_path", macro_path)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "file_path":
            if value is not None:
                file_path_str = str(value)
            else:
                file_path_str = ""
            self._update_macro_path(file_path_str)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        file_path_str = self.get_parameter_value("file_path")
        if file_path_str is not None:
            file_path_str = str(file_path_str)
        else:
            file_path_str = ""
        self._update_macro_path(file_path_str)
