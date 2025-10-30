from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class PathAddExtension(DataNode):
    """Add or replace a file extension on a path."""

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
            tooltip="The file path to add or replace the extension on.",
            placeholder_text="Example: /path/to/file.txt",
        )
        self.path_input.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.path_input)

        # Add input parameter for the extension
        self.add_parameter(
            ParameterString(
                name="extension",
                default_value="",
                tooltip="The file extension to add (with or without leading dot, e.g., 'txt' or '.txt').",
                placeholder_text="Example: txt or .txt",
            )
        )

        # Add option to strip query parameters
        self.add_parameter(
            ParameterBool(
                name="strip_query_params",
                default_value=True,
                tooltip="If True, remove query parameters from the path. If False, keep query parameters but change the extension.",
            )
        )

        # Add output parameter for the modified path
        self.add_parameter(
            ParameterString(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The path with the new extension.",
                tooltip="The path with the extension added or replaced.",
            )
        )

    def _add_extension(self) -> None:
        """Add or replace extension on the path and update output parameter."""
        # Get input values
        path_str = self.get_parameter_value("path")
        extension = self.get_parameter_value("extension")
        strip_query_params = self.get_parameter_value("strip_query_params")

        # Initialize output
        output_path = ""

        if path_str:
            path_str = str(path_str).strip()
            if extension:
                extension_str = str(extension).strip()
            else:
                extension_str = ""

            # Normalize extension (ensure it starts with a dot)
            if extension_str and not extension_str.startswith("."):
                extension_str = f".{extension_str}"

            # Split path and query parameters
            if "?" in path_str:
                path_part, query_part = path_str.split("?", 1)
                query_params = f"?{query_part}"
            else:
                path_part = path_str
                query_params = ""

            # Convert to Path object
            path_obj = Path(path_part)

            # Replace extension (or add if none exists)
            if path_obj.name:  # Has a filename component
                # Replace the extension
                if extension_str:
                    new_path_obj = path_obj.with_suffix(extension_str)
                else:
                    new_path_obj = path_obj.with_suffix("")
            elif extension_str:
                # No filename, just add extension to the path
                new_path_obj = Path(str(path_obj) + extension_str)
            else:
                new_path_obj = path_obj

            # Build output path
            output_path = str(new_path_obj)

            # Add query parameters back if not stripping
            if not strip_query_params and query_params:
                output_path = f"{output_path}{query_params}"

        # Set the output
        self.set_parameter_value("output", output_path)
        self.publish_update_to_parameter("output", output_path)
        self.parameter_output_values["output"] = output_path

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ("path", "extension", "strip_query_params"):
            self._add_extension()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Add the extension
        self._add_extension()
