from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.progress_bar_component import ProgressBarComponent
from griptape_nodes.retained_mode.events.os_events import (
    CopyFileRequest,
    CopyFileResultFailure,
    CopyFileResultSuccess,
    CopyTreeRequest,
    CopyTreeResultFailure,
    CopyTreeResultSuccess,
    DeleteFileRequest,
    DeleteFileResultFailure,
    DeleteFileResultSuccess,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.files.file_operation_base import FileOperationBaseNode


class MoveStatus(Enum):
    """Status of a move attempt."""

    PENDING = "pending"
    COPY_SUCCESS = "copy_success"  # Copy succeeded, delete pending
    SUCCESS = "success"  # Both copy and delete succeeded
    FAILED = "failed"  # Copy failed
    DELETE_FAILED = "delete_failed"  # Copy succeeded but delete failed
    INVALID = "invalid"  # Invalid or inaccessible path


@dataclass
class MoveFileInfo:
    """Information about a file/directory move attempt."""

    source_path: str  # Workspace-relative path
    destination_path: str  # Destination path
    is_directory: bool
    status: MoveStatus = MoveStatus.PENDING
    failure_reason: str | None = None
    moved_paths: list[str] = field(default_factory=list)  # Paths actually moved (from OS result)
    explicitly_requested: bool = False  # True if user specified this path, False if discovered via glob


class MoveFiles(FileOperationBaseNode):
    """Move files and/or directories from source to destination.

    Directories are moved recursively with all their contents.
    Implemented as copy + delete operation.
    Accepts single path (str) or multiple paths (list[str]) for source_paths.
    Supports glob patterns (e.g., "/path/to/*.txt") for matching multiple files.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Define converter function for extracting artifact values
        def convert_artifact_to_string(value: Any) -> Any:
            """Converter function to extract string values from artifacts."""
            # If already a string, return as-is to avoid recursion
            if isinstance(value, str):
                return value
            # If None or empty, return as-is
            if value is None:
                return None
            # Extract from artifact
            return self._extract_artifacts_from_value(value)

        # Input parameter - accepts any type, will be normalized to list[str]
        self.source_paths = ParameterList(
            name="source_paths",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "list", "any"],
            default_value=[],
            tooltip="Path(s) to file(s) or directory(ies) to move. Supports glob patterns (e.g., '/path/*.txt').",
            converters=[convert_artifact_to_string],
        )
        self.add_parameter(self.source_paths)

        # Destination directory parameter
        self.destination_path = Parameter(
            name="destination_path",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            default_value="",
            tooltip="Destination directory where files will be moved.",
            ui_options={"placeholder_text": "Enter destination directory path"},
        )
        self.destination_path.add_trait(
            FileSystemPicker(
                allow_files=False,
                allow_directories=True,
                multiple=False,
            )
        )
        self.add_parameter(self.destination_path)

        # Overwrite parameter
        self.overwrite = Parameter(
            name="overwrite",
            type="bool",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            default_value=False,
            tooltip="Whether to overwrite existing files at destination (default: False).",
        )
        self.add_parameter(self.overwrite)

        # Output parameter
        self.moved_paths_output = Parameter(
            name="moved_paths",
            allow_input=False,
            allow_property=False,
            output_type="list[str]",
            default_value=[],
            tooltip="List of all destination paths that were moved.",
        )
        self.add_parameter(self.moved_paths_output)

        # Create progress bar component
        self.progress_component = ProgressBarComponent(self)
        self.progress_component.add_property_parameters()

        # Create status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the move result",
            result_details_placeholder="Details on the move attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def _expand_glob_pattern(self, path_str: str, all_targets: list[MoveFileInfo]) -> None:
        """Expand a glob pattern using ListDirectoryRequest and add matches to all_targets.

        Args:
            path_str: Glob pattern (e.g., "/path/to/*.txt")
            all_targets: List to append matching MoveFileInfo entries to
        """
        # Parse the pattern into directory and pattern parts
        path = Path(path_str)

        # If the pattern has multiple parts with wildcards, we need to handle parent resolution
        # For now, we'll support patterns where only the last component has wildcards
        if self._is_glob_pattern(str(path.parent)):
            # Parent directory contains wildcards - this is more complex, treat as invalid
            all_targets.append(
                MoveFileInfo(
                    source_path=path_str,
                    destination_path="",
                    is_directory=False,
                    status=MoveStatus.INVALID,
                    failure_reason="Glob patterns in parent directories are not supported",
                )
            )
            return

        # Directory is the parent, pattern is the name with wildcards
        directory_path = str(path.parent)
        pattern = path.name

        # Use ListDirectoryRequest and filter manually with fnmatch
        request = ListDirectoryRequest(directory_path=directory_path, show_hidden=True, workspace_only=False)
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ListDirectoryResultSuccess):
            # Filter entries matching the pattern
            matching_entries = [entry for entry in result.entries if fnmatch(entry.name, pattern)]
            if not matching_entries:
                # No matches found - treat as invalid
                all_targets.append(
                    MoveFileInfo(
                        source_path=path_str,
                        destination_path="",
                        is_directory=False,
                        status=MoveStatus.INVALID,
                        failure_reason=f"No files match pattern '{pattern}'",
                    )
                )
            else:
                # Add all matching entries as PENDING (explicitly requested via glob pattern)
                all_targets.extend(
                    MoveFileInfo(
                        source_path=entry.path,
                        destination_path="",  # Will be set during move operation
                        is_directory=entry.is_dir,
                        status=MoveStatus.PENDING,
                        explicitly_requested=True,
                    )
                    for entry in matching_entries
                )
        else:
            # Directory doesn't exist or can't be accessed
            failure_msg = (
                result.failure_reason.value if isinstance(result, ListDirectoryResultFailure) else "Unknown error"
            )
            all_targets.append(
                MoveFileInfo(
                    source_path=path_str,
                    destination_path="",
                    is_directory=False,
                    status=MoveStatus.INVALID,
                    failure_reason=failure_msg,
                )
            )

    def _collect_all_move_targets(self, paths: list[str]) -> list[MoveFileInfo]:
        """Collect all files/directories that will be moved.

        Handles both explicit paths and glob patterns (e.g., "/path/to/*.txt").
        Glob patterns match individual files in a directory, not subdirectories.

        Returns:
            List of MoveFileInfo with status set (PENDING for valid paths, INVALID for invalid paths)
        """
        return self._collect_all_files(
            paths=paths,
            info_class=MoveFileInfo,
            pending_status=MoveStatus.PENDING,
            invalid_status=MoveStatus.INVALID,
            expand_glob_pattern=self._expand_glob_pattern,
        )

    def _execute_move(self, target: MoveFileInfo, destination_dir: str, *, overwrite: bool) -> None:
        """Execute move operation for a single target (copy + delete).

        Args:
            target: MoveFileInfo with source_path set
            destination_dir: Destination directory
            overwrite: Whether to overwrite existing files
        """
        # Resolve destination path
        destination_path = self._resolve_destination_path(target.source_path, destination_dir)
        target.destination_path = destination_path

        # Step 1: Copy to destination
        if target.is_directory:
            # Use CopyTreeRequest for directories
            copy_request = CopyTreeRequest(
                source_path=target.source_path,
                destination_path=destination_path,
                dirs_exist_ok=overwrite,
            )
            copy_result = GriptapeNodes.handle_request(copy_request)

            if isinstance(copy_result, CopyTreeResultFailure):
                target.status = MoveStatus.FAILED
                target.failure_reason = f"Copy failed: {copy_result.failure_reason.value}"
                return  # Don't delete if copy failed

            if not isinstance(copy_result, CopyTreeResultSuccess):
                target.status = MoveStatus.FAILED
                target.failure_reason = "Unexpected result type from copy operation"
                return

            # Copy succeeded for directory
            target.status = MoveStatus.COPY_SUCCESS
            target.moved_paths = [destination_path]
        else:
            # Use CopyFileRequest for files
            copy_request = CopyFileRequest(
                source_path=target.source_path,
                destination_path=destination_path,
                overwrite=overwrite,
            )
            copy_result = GriptapeNodes.handle_request(copy_request)

            if isinstance(copy_result, CopyFileResultFailure):
                target.status = MoveStatus.FAILED
                target.failure_reason = f"Copy failed: {copy_result.failure_reason.value}"
                return  # Don't delete if copy failed

            if not isinstance(copy_result, CopyFileResultSuccess):
                target.status = MoveStatus.FAILED
                target.failure_reason = "Unexpected result type from copy operation"
                return

            # Copy succeeded for file
            target.status = MoveStatus.COPY_SUCCESS
            target.moved_paths = [destination_path]

        # Step 2: Delete source (only if copy succeeded)
        delete_request = DeleteFileRequest(path=target.source_path, workspace_only=False)
        delete_result = GriptapeNodes.handle_request(delete_request)

        if isinstance(delete_result, DeleteFileResultFailure):
            target.status = MoveStatus.DELETE_FAILED
            target.failure_reason = f"Copy succeeded but delete failed: {delete_result.failure_reason.value}"
            return

        if not isinstance(delete_result, DeleteFileResultSuccess):
            target.status = MoveStatus.DELETE_FAILED
            target.failure_reason = "Copy succeeded but delete returned unexpected result type"
            return

        # SUCCESS PATH AT END - both copy and delete succeeded
        target.status = MoveStatus.SUCCESS

    def _format_result_details(self, all_targets: list[MoveFileInfo]) -> str:
        """Format detailed results showing what happened to each file."""
        lines = []

        # Count outcomes
        succeeded = [t for t in all_targets if t.status == MoveStatus.SUCCESS]
        failed = [t for t in all_targets if t.status == MoveStatus.FAILED]
        delete_failed = [t for t in all_targets if t.status == MoveStatus.DELETE_FAILED]
        invalid = [t for t in all_targets if t.status == MoveStatus.INVALID]

        # Summary line
        valid_targets = [t for t in all_targets if t.status != MoveStatus.INVALID]
        lines.append(f"Moved {len(succeeded)}/{len(valid_targets)} valid items")

        # Show delete failures if any (copy succeeded but delete failed)
        if delete_failed:
            lines.append(f"\nCopy succeeded but delete failed ({len(delete_failed)}):")
            for target in delete_failed:
                reason = target.failure_reason or "Unknown error"
                lines.append(f"  ⚠️ {target.source_path}: {reason}")

        # Show failures if any
        if failed:
            lines.append(f"\nFailed to move ({len(failed)}):")
            for target in failed:
                reason = target.failure_reason or "Unknown error"
                lines.append(f"  ❌ {target.source_path}: {reason}")

        # Show invalid paths if any
        if invalid:
            lines.append(f"\nInvalid paths ({len(invalid)}):")
            for target in invalid:
                reason = target.failure_reason or "Invalid or inaccessible"
                lines.append(f"  ⚠️ {target.source_path}: {reason}")

        # Show successfully moved files
        if succeeded:
            lines.append(f"\nSuccessfully moved ({len(succeeded)}):")
            for target in succeeded:
                if target.is_directory:
                    lines.append(f"  📁 {target.source_path} → {target.destination_path}")
                else:
                    lines.append(f"  📄 {target.source_path} → {target.destination_path}")

        return "\n".join(lines)

    def process(self) -> None:
        """Execute the file move operation."""
        self._clear_execution_status()
        self.progress_component.reset()

        # Get parameter values
        source_paths_raw = self.get_parameter_list_value("source_paths")
        destination_dir = self.get_parameter_value("destination_path")
        overwrite = self.get_parameter_value("overwrite") or False

        # FAILURE CASE: Empty source paths
        if not source_paths_raw:
            msg = f"{self.name} attempted to move with empty source paths. Failed due to no paths provided"
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Normalize to list of strings (get_parameter_list_value flattens, but we need to ensure strings)
        # Also extract values from artifacts
        source_paths = [self._extract_value_from_artifact(p) for p in source_paths_raw if p is not None]

        # Remove duplicates
        source_paths = list(set(source_paths))

        # FAILURE CASE: Empty destination
        if not destination_dir:
            msg = f"{self.name} attempted to move but destination path is empty. Failed due to no destination provided"
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Determine if destination is a directory or file path
        # We'll validate this per-file in _resolve_destination_path
        # For now, just proceed with move operations

        # Collect all targets (includes INVALID status for bad paths)
        all_targets = self._collect_all_move_targets(source_paths)

        # Separate valid and invalid targets
        pending_targets = [t for t in all_targets if t.status == MoveStatus.PENDING]

        # FAILURE CASE: No valid targets at all
        if not pending_targets:
            msg = f"{self.name} attempted to move but all source paths were invalid. No files moved"
            details = self._format_result_details(all_targets)
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # Check if destination looks like a file path (has extension)
        destination_path_obj = Path(destination_dir)
        destination_is_file_path = bool(destination_path_obj.suffix)

        # FAILURE CASE: Multiple source files but destination is a file path
        if destination_is_file_path and len(pending_targets) > 1:
            msg = f"{self.name} attempted to move {len(pending_targets)} files to a single file path '{destination_dir}'. Cannot move multiple files to a single file destination. Use a directory path instead."
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Execute moves for all explicitly requested items
        explicitly_requested = [t for t in pending_targets if t.explicitly_requested]

        # Initialize progress bar with total number of files to move
        self.progress_component.initialize(len(explicitly_requested))

        for target in explicitly_requested:
            self._execute_move(target, destination_dir, overwrite=overwrite)
            # Increment progress after each file is processed
            self.progress_component.increment()

        # Collect all successfully moved paths (only fully successful moves)
        all_moved_paths: list[str] = []
        for target in explicitly_requested:
            if target.status == MoveStatus.SUCCESS:
                all_moved_paths.extend(target.moved_paths)

        # Only report on explicitly requested items
        requested_targets = [t for t in all_targets if t.explicitly_requested]

        # Determine success/failure
        # Consider it successful if at least one file was fully moved (copy + delete)
        succeeded_count = len([t for t in requested_targets if t.status == MoveStatus.SUCCESS])

        # FAILURE CASE: Zero files were successfully moved
        if succeeded_count == 0:
            msg = f"{self.name} failed to move any files"
            details = self._format_result_details(requested_targets)
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # SUCCESS PATH AT END (even if some failed, as long as at least one succeeded)
        # Set output parameters
        self.set_parameter_value(self.moved_paths_output.name, all_moved_paths)
        self.parameter_output_values[self.moved_paths_output.name] = all_moved_paths

        # Generate detailed result message (only for explicitly requested items)
        details = self._format_result_details(requested_targets)

        self._set_status_results(was_successful=True, result_details=details)
