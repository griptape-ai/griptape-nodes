from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class FilePathComponents(DataNode):
    """Extract various components from a file path."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameter for the path
        self.path_input = ParameterString(
            name="path",
            default_value="",
            tooltip="The file path to extract components from.",
        )
        self.path_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.path_input)

        # Add output parameters for path components
        self.add_parameter(
            ParameterString(
                name="filename",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The filename with extension, query parameters stripped (e.g., 'file.txt').",
                placeholder_text="Example: file.txt",
            )
        )

        self.add_parameter(
            ParameterString(
                name="stem",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The filename without extension (e.g., 'file').",
                placeholder_text="Example:file",
            )
        )

        self.add_parameter(
            ParameterString(
                name="extension",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The file extension including the dot (e.g., '.txt').",
                placeholder_text="Example:.txt",
            )
        )

        self.add_parameter(
            ParameterString(
                name="parent",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The parent directory path.",
                placeholder_text="Example: /path/to/directory",
            )
        )

        self.add_parameter(
            ParameterString(
                name="parent_name",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The name of the immediate parent directory (e.g., 'directory').",
                placeholder_text="Example: directory",
            )
        )

        self.add_parameter(
            ParameterString(
                name="query_params",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The query parameters from the path (e.g., 't=123456').",
                placeholder_text="Example: t=123456",
            )
        )

    def _extract_path_components(self, path_str: str) -> None:
        """Extract path components and update output parameters."""
        # Initialize all outputs to empty strings
        filename = ""
        stem = ""
        extension = ""
        parent = ""
        parent_name = ""
        query_params = ""

        # Extract components if path is provided
        if path_str:
            # Split path and query parameters
            if "?" in path_str:
                path_part, query_part = path_str.split("?", 1)
                query_params = query_part
            else:
                path_part = path_str
                query_params = ""

            # Convert to Path object (without query params)
            path_obj = Path(path_part)

            # Extract components (without query params)
            filename = path_obj.name
            stem = path_obj.stem
            extension = path_obj.suffix
            parent = str(path_obj.parent) if path_obj.parent else ""
            parent_name = path_obj.parent.name if path_obj.parent else ""

        # Set output values and publish updates
        self.parameter_output_values["filename"] = filename
        self.parameter_output_values["stem"] = stem
        self.parameter_output_values["extension"] = extension
        self.parameter_output_values["parent"] = parent
        self.parameter_output_values["parent_name"] = parent_name
        self.parameter_output_values["query_params"] = query_params

        self.publish_update_to_parameter("filename", filename)
        self.publish_update_to_parameter("stem", stem)
        self.publish_update_to_parameter("extension", extension)
        self.publish_update_to_parameter("parent", parent)
        self.publish_update_to_parameter("parent_name", parent_name)
        self.publish_update_to_parameter("query_params", query_params)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "path":
            # Convert value to string if needed
            path_str = str(value) if value is not None else ""
            self._extract_path_components(path_str)

        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        pass

    def process(self) -> None:
        # Get the input path
        path_str = self.get_parameter_value("path")
        if path_str is not None:
            path_str = str(path_str)
        else:
            path_str = ""

        self._extract_path_components(path_str)
