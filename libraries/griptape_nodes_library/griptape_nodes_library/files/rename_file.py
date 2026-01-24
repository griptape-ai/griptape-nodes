from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    DeleteFileResultFailure,
    RenameFileRequest,
    RenameFileResultFailure,
    RenameFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes_library.files.file_operation_base import FileOperationBaseNode
from griptape_nodes_library.utils.frame_number_mixin import FrameNumberMixin


class RenameFile(FrameNumberMixin, FileOperationBaseNode):
    """Rename a file or directory.

    Can rename to a new name in the same directory or to a full path.
    Supports overwriting existing files/directories if overwrite is enabled.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Old path parameter
        self.old_path = ParameterString(
            name="old_path",
            tooltip="Current path of file/directory to rename.",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="",
        )
        self.old_path.add_trait(
            FileSystemPicker(
                allow_files=True,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.old_path)

        # New path parameter
        self.new_path = ParameterString(
            name="new_path",
            tooltip="New path/name for the file/directory. Can be full path or just new name (if same directory). If just a filename (e.g., 'newfile.txt'), it will rename in place.",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="",
            placeholder_text="newfile.txt or /path/to/newfile.txt",
        )
        self.add_parameter(self.new_path)

        # Overwrite parameter
        self.overwrite = Parameter(
            name="overwrite",
            type="bool",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            default_value=False,
            tooltip="Whether to overwrite if new_path exists (default: False). If False and new_path exists, operation fails.",
        )
        self.add_parameter(self.overwrite)

        # Add frame number parameters via mixin
        self._add_frame_number_parameters()

        # Output parameters
        self.old_path_output = Parameter(
            name="old_path_output",
            allow_input=False,
            allow_property=False,
            output_type="str",
            default_value="",
            tooltip="The original path that was renamed.",
        )
        self.add_parameter(self.old_path_output)

        self.new_path_output = Parameter(
            name="new_path_output",
            allow_input=False,
            allow_property=False,
            output_type="str",
            default_value="",
            tooltip="The new path after renaming.",
        )
        self.add_parameter(self.new_path_output)

        # Create status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the rename result",
            result_details_placeholder="Details on the rename attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that required parameters are provided."""
        exceptions = []

        # Get parameter values
        old_path = self.get_parameter_value("old_path")
        new_path = self.get_parameter_value("new_path")

        # FAILURE CASE: Empty old_path
        if not old_path:
            exceptions.append(
                ValueError(
                    f"{self.name} attempted to rename but old_path is empty. Failed due to no source path provided"
                )
            )

        # FAILURE CASE: Empty new_path
        if not new_path:
            exceptions.append(
                ValueError(
                    f"{self.name} attempted to rename but new_path is empty. Failed due to no destination path provided"
                )
            )

        # Call parent validation
        parent_exceptions = super().validate_before_node_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        # Handle frame number parameter visibility
        self._handle_frame_number_parameter_change(parameter, value)

    def _resolve_new_path(self, old_path: str, new_path: str) -> str:
        """Resolve the full new path.

        If new_path is just a filename (no directory), use same directory as old_path.
        Otherwise, use new_path as-is.
        If add_frame_number is enabled, insert padded frame number into filename.

        Args:
            old_path: Current path of file/directory
            new_path: New path or name

        Returns:
            Full resolved new path
        """
        # Clean paths to remove newlines/carriage returns that cause Windows errors
        old_path = GriptapeNodes.OSManager().sanitize_path_string(old_path)
        new_path = GriptapeNodes.OSManager().sanitize_path_string(new_path)

        # Apply frame number padding if enabled
        new_path = self._apply_frame_number_if_enabled(new_path)

        new_path_obj = Path(new_path)
        old_path_obj = Path(old_path)

        # If new_path is absolute (full path), use it as-is
        # This works cross-platform:
        # - Unix: paths starting with / are absolute
        # - Windows: paths with drive letter (C:\) or UNC (\\server\share) are absolute
        if new_path_obj.is_absolute():
            return str(new_path_obj)

        # Check if new_path is just a filename (no directory parts)
        # Path.parent for a simple filename returns Path('.') on all platforms
        # A simple filename has only one part and parent is "."
        parent_path = new_path_obj.parent
        is_just_filename = str(parent_path) in {".", ""} and len(new_path_obj.parts) == 1

        if is_just_filename:
            # Just a filename - use old_path's parent directory
            return str(old_path_obj.parent / new_path_obj.name)

        # Otherwise, it's a relative path with directory parts - return normalized
        # Path normalizes separators automatically (handles / and \ cross-platform)
        return str(new_path_obj)


    def process(self) -> None:
        """Execute the file rename operation."""
        self._clear_execution_status()

        # Get parameter values
        old_path_raw = self.get_parameter_value("old_path")
        new_path_input = self.get_parameter_value("new_path")
        overwrite = self.get_parameter_value("overwrite") or False

        # Extract value from artifacts and resolve localhost URLs to workspace paths
        old_path = self._extract_value_from_artifact(old_path_raw)
        new_path_input = self._extract_value_from_artifact(new_path_input)

        # Clean paths to remove newlines/carriage returns that cause Windows errors
        old_path = GriptapeNodes.OSManager().sanitize_path_string(old_path)
        new_path_input = GriptapeNodes.OSManager().sanitize_path_string(new_path_input)

        # Resolve new path
        new_path = self._resolve_new_path(old_path, new_path_input)

        # FAILURE CASE: Old path doesn't exist
        old_path_result = self._check_path_exists(old_path)
        if not old_path_result.exists:
            msg = f"{self.name} attempted to rename but old_path does not exist: {old_path}"
            self.set_parameter_value(self.old_path_output.name, "")
            self.set_parameter_value(self.new_path_output.name, "")
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # FAILURE CASE: New path exists and overwrite is False
        new_path_result = self._check_path_exists(new_path)
        if new_path_result.exists and not overwrite:
            msg = f"{self.name} attempted to rename but new_path already exists and overwrite is False: {new_path}"
            self.set_parameter_value(self.old_path_output.name, "")
            self.set_parameter_value(self.new_path_output.name, "")
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # If overwrite is True and new_path exists, delete it first
        if new_path_result.exists and overwrite:
            delete_request = DeleteFileRequest(path=new_path, workspace_only=False)
            delete_result = GriptapeNodes.handle_request(delete_request)

            if isinstance(delete_result, DeleteFileResultFailure):
                failure_reason = (
                    delete_result.failure_reason.value
                    if hasattr(delete_result.failure_reason, "value")
                    else "Unknown error"
                )
                # Include detailed error message if available
                error_details = ""
                if delete_result.result_details:
                    # ResultDetails.__str__() returns concatenated messages from all ResultDetail objects
                    error_details = f" - {delete_result.result_details}"
                msg = f"{self.name} attempted to rename but failed to delete existing destination: {failure_reason}{error_details}"
                self.set_parameter_value(self.old_path_output.name, "")
                self.set_parameter_value(self.new_path_output.name, "")
                self._set_status_results(was_successful=False, result_details=msg)
                return

        # Create parent directory of new_path if it doesn't exist
        new_path_obj = Path(new_path)
        parent_dir = new_path_obj.parent
        if parent_dir:
            # Check if parent exists as a file (not a directory) - this would prevent creating the directory
            if parent_dir.exists() and not parent_dir.is_dir():
                msg = (
                    f"{self.name} cannot rename to '{new_path_obj.name}' because the parent path '{parent_dir}' "
                    f"exists as a file, not a directory. Please remove or rename the conflicting file first."
                )
                self.set_parameter_value(self.old_path_output.name, "")
                self.set_parameter_value(self.new_path_output.name, "")
                self._set_status_results(was_successful=False, result_details=msg)
                return

            # Only create directory if it doesn't exist (exist_ok=True handles race conditions)
            if not parent_dir.exists():
                try:
                    parent_dir.mkdir(parents=True, exist_ok=True)
                except (PermissionError, OSError) as e:
                    msg = f"{self.name} attempted to rename but failed to create parent directory: {e}"
                    self.set_parameter_value(self.old_path_output.name, "")
                    self.set_parameter_value(self.new_path_output.name, "")
                    self._set_status_results(was_successful=False, result_details=msg)
                    return

        # SUCCESS PATH AT END: Execute rename
        rename_request = RenameFileRequest(old_path=old_path, new_path=new_path, workspace_only=False)
        rename_result = GriptapeNodes.handle_request(rename_request)

        if isinstance(rename_result, RenameFileResultFailure):
            failure_reason = (
                rename_result.failure_reason.value
                if hasattr(rename_result.failure_reason, "value")
                else "Unknown error"
            )
            # Include detailed error message if available
            error_details = ""
            if rename_result.result_details:
                # ResultDetails.__str__() returns concatenated messages from all ResultDetail objects
                error_details = f" - {rename_result.result_details}"
            msg = f"{self.name} failed to rename: {failure_reason}{error_details}"
            self.set_parameter_value(self.old_path_output.name, "")
            self.set_parameter_value(self.new_path_output.name, "")
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # SUCCESS PATH AT END - result must be RenameFileResultSuccess (only two possible types)
        success_result = cast("RenameFileResultSuccess", rename_result)
        self.set_parameter_value(self.old_path_output.name, success_result.old_path)
        self.set_parameter_value(self.new_path_output.name, success_result.new_path)
        self.parameter_output_values[self.old_path_output.name] = success_result.old_path
        self.parameter_output_values[self.new_path_output.name] = success_result.new_path

        self._set_status_results(was_successful=True, result_details="File renamed successfully")
