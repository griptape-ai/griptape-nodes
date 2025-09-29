from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.os_events import ListDirectoryRequest, ListDirectoryResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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

        self.show_hidden = Parameter(
            name="show_hidden",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            type="bool",
            default_value=False,
            tooltip="Whether to show hidden files/folders.",
        )

        self.add_parameter(self.directory_path)
        self.add_parameter(self.show_hidden)

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
        show_hidden = self.parameter_values["show_hidden"]

        # Create the os_events request
        request = ListDirectoryRequest(
            directory_path=directory_path if directory_path else None,
            show_hidden=show_hidden,
            workspace_only=False,  # Allow system-wide browsing
        )

        # Send request through GriptapeNodes.handle_request
        try:
            result = GriptapeNodes.handle_request(request)
        except Exception as e:
            msg = f"Error while listing directory: {e!s}"
            raise RuntimeError(msg) from e

        if isinstance(result, ListDirectoryResultSuccess):
            # Filter to only include files (not directories)
            file_entries = list(result.entries)

            file_paths = [entry.path for entry in file_entries]
            file_names = [entry.name for entry in file_entries]

            # Set output values
            self.parameter_output_values["file_paths"] = file_paths
            self.parameter_output_values["file_names"] = file_names
            self.parameter_output_values["file_count"] = len(file_paths)

            # Also set in parameter_values for get_value compatibility
            self.parameter_values["file_paths"] = file_paths
            self.parameter_values["file_names"] = file_names
            self.parameter_values["file_count"] = len(file_paths)
        else:
            # Handle failure case
            error_msg = getattr(result, "error_message", "Unknown error occurred")
            msg = f"Failed to list directory: {error_msg}"
            raise TypeError(msg) from None
