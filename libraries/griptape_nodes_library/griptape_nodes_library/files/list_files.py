import logging
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.os_events import (
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")
LIST_OPTIONS = [
    "List files and folders",
    "List files only",
    "List folders only",
]


class ListFiles(SuccessFailureNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameters
        self.directory_path = ParameterString(
            name="directory_path",
            allow_output=False,
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

        self.list_options = ParameterString(
            name="list_options",
            allow_output=False,
            default_value=LIST_OPTIONS[0],
            tooltip="The options for the list files and folders.",
            traits={Options(choices=LIST_OPTIONS)},
        )

        self.show_hidden = ParameterBool(
            name="show_hidden",
            allow_output=False,
            default_value=False,
            tooltip="Whether to show hidden files/folders.",
        )

        self.use_absolute_paths = ParameterBool(
            name="use_absolute_paths",
            allow_output=False,
            default_value=False,
            tooltip="Whether to return absolute paths. If False, returns paths as provided by the system (may be relative or absolute).",
        )

        self.add_parameter(self.directory_path)
        self.add_parameter(self.show_hidden)
        self.add_parameter(self.list_options)
        self.add_parameter(self.use_absolute_paths)

        # Add output parameters
        self.add_parameter(
            Parameter(
                name="file_paths",
                allow_input=False,
                allow_property=False,
                output_type="list",
                default_value=[],
                tooltip="List of full file paths found in the directory.",
            )
        )

        self.add_parameter(
            Parameter(
                name="file_names",
                allow_input=False,
                allow_property=False,
                output_type="list",
                default_value=[],
                tooltip="List of file names (without path) found in the directory.",
            )
        )

        self.add_parameter(
            ParameterInt(
                name="file_count",
                allow_input=False,
                allow_property=False,
                default_value=0,
                tooltip="Total number of files found.",
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the list file result",
            result_details_placeholder="Details on the list file attempt will be presented here.",
        )

    def _filter_entries(self, entries: list, *, include_files: bool, include_folders: bool) -> list:
        """Filter entries based on include_files and include_folders."""
        filtered_entries = []
        for entry in entries:
            if entry.is_dir:
                if include_folders:
                    filtered_entries.append(entry)
            elif include_files:
                filtered_entries.append(entry)
        return filtered_entries

    def _convert_paths(self, entries: list, *, use_absolute_paths: bool) -> list[str]:
        """Extract paths from entries, optionally converting to absolute paths."""
        file_paths = []
        os_manager = GriptapeNodes.OSManager()
        for entry in entries:
            if use_absolute_paths:
                entry_path = Path(entry.path)
                if not entry_path.is_absolute():
                    workspace_path = GriptapeNodes.ConfigManager().workspace_path
                    combined_path = workspace_path / entry_path
                    absolute_path = os_manager.resolve_path_safely(combined_path)
                    file_paths.append(str(absolute_path))
                else:
                    absolute_path = os_manager.resolve_path_safely(entry_path)
                    file_paths.append(str(absolute_path))
            else:
                file_paths.append(entry.path)
        return file_paths

    def process(self) -> None:
        self._clear_execution_status()
        directory_path = self.get_parameter_value("directory_path")
        show_hidden = self.get_parameter_value("show_hidden")
        list_options = self.get_parameter_value("list_options")
        use_absolute_paths = self.get_parameter_value("use_absolute_paths")

        # Determine include_files and include_folders based on list_options
        if list_options == LIST_OPTIONS[0]:  # "List files and folders"
            include_files = True
            include_folders = True
        elif list_options == LIST_OPTIONS[1]:  # "List files only"
            include_files = True
            include_folders = False
        elif list_options == LIST_OPTIONS[2]:  # "List folders only"
            include_files = False
            include_folders = True
        else:
            # Fallback to default if invalid option
            msg = f"{self.name}: Invalid list options: {list_options}, listing all files and folders"
            logger.warning(msg)
            include_files = True
            include_folders = True

        # Create the os_events request
        request = ListDirectoryRequest(
            directory_path=directory_path if directory_path else None,
            show_hidden=show_hidden,
            workspace_only=False,  # Allow system-wide browsing
        )

        # Send request through GriptapeNodes.handle_request
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ListDirectoryResultFailure):
            error_msg = getattr(result, "error_message", "Unknown error occurred")
            msg = f"{self.name} failed to list directory: {error_msg}"
            self._set_status_results(was_successful=False, result_details=f"Failure: {msg}")
            return

        if not isinstance(result, ListDirectoryResultSuccess):
            msg = f"{self.name} received unexpected result type from directory listing"
            self._set_status_results(was_successful=False, result_details=f"Failure: {msg}")
            return

        filtered_entries = self._filter_entries(
            result.entries, include_files=include_files, include_folders=include_folders
        )
        file_paths = self._convert_paths(filtered_entries, use_absolute_paths=use_absolute_paths)
        file_names = [entry.name for entry in filtered_entries]

        # Set output values
        self.set_parameter_value("file_paths", file_paths)
        self.set_parameter_value("file_names", file_names)
        self.set_parameter_value("file_count", len(file_paths))
        self._set_status_results(was_successful=True, result_details="Success")
