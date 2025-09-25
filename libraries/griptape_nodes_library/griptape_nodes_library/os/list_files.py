import os
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class ListFiles(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameters
        self.directory_path = Parameter(
            name="directory_path",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="The directory path to list files from.",
        )
        self.directory_path.add_trait(
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
                multiple=False,
            )
        )

        self.include_subdirectories = Parameter(
            name="include_subdirectories",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            type="bool",
            default_value=False,
            tooltip="Whether to include files from subdirectories recursively.",
        )

        self.file_pattern = Parameter(
            name="file_pattern",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            type="str",
            default_value="*",
            tooltip="File pattern to match (e.g., '*.py', '*.txt', '*'). Supports glob patterns.",
        )

        self.add_parameter(self.directory_path)
        self.add_parameter(self.include_subdirectories)
        self.add_parameter(self.file_pattern)

        # Add output parameters
        self.add_parameter(
            Parameter(
                name="file_paths",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="list",
                default_value=[],
                tooltip="List of file paths found in the directory.",
            )
        )

        self.add_parameter(
            Parameter(
                name="file_names",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="list",
                default_value=[],
                tooltip="List of file names (without path) found in the directory.",
            )
        )

        self.add_parameter(
            Parameter(
                name="file_count",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="int",
                default_value=0,
                tooltip="Total number of files found.",
            )
        )

    def process(self) -> None:
        directory_path = self.parameter_values["directory_path"]
        include_subdirectories = self.parameter_values["include_subdirectories"]
        file_pattern = self.parameter_values["file_pattern"]

        if not directory_path:
            msg = "Directory path cannot be empty"
            raise ValueError(msg)

        directory = Path(directory_path)
        if not directory.exists():
            msg = f"Directory does not exist: {directory_path}"
            raise FileNotFoundError(msg)

        if not directory.is_dir():
            msg = f"Path is not a directory: {directory_path}"
            raise ValueError(msg)

        file_paths = []
        file_names = []

        try:
            if include_subdirectories:
                # Use recursive glob for subdirectories
                for file_path in directory.rglob(file_pattern):
                    if file_path.is_file():
                        file_paths.append(str(file_path))
                        file_names.append(file_path.name)
            else:
                # Use non-recursive glob for current directory only
                for file_path in directory.glob(file_pattern):
                    if file_path.is_file():
                        file_paths.append(str(file_path))
                        file_names.append(file_path.name)

            # Sort the lists for consistent output
            file_paths.sort()
            file_names.sort()

        except Exception as e:
            msg = f"Error listing files: {e}"
            raise RuntimeError(msg) from e

        # Set output values
        self.parameter_output_values["file_paths"] = file_paths
        self.parameter_output_values["file_names"] = file_names
        self.parameter_output_values["file_count"] = len(file_paths)

        # Also set in parameter_values for get_value compatibility
        self.parameter_values["file_paths"] = file_paths
        self.parameter_values["file_names"] = file_names
        self.parameter_values["file_count"] = len(file_paths)
