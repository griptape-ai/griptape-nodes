from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    DeleteFileResultFailure,
    GetFileInfoRequest,
    GetFileInfoResultSuccess,
    RenameFileRequest,
    RenameFileResultFailure,
    RenameFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.files.copy_files import CopyFiles
from griptape_nodes_library.files.file_operation_base import BaseFileOperationInfo


class MoveStatus(Enum):
    """Status of a move attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    INVALID = "invalid"  # Invalid or inaccessible path


@dataclass
class MoveFileInfo(BaseFileOperationInfo):
    """Information about a file/directory move attempt."""

    status: MoveStatus = MoveStatus.PENDING
    moved_paths: list[str] = field(default_factory=list)  # Paths actually moved (from OS result)


class MoveFiles(CopyFiles):
    """Move files and/or directories from source to destination.

    Directories are moved recursively with all their contents.
    Uses RenameFileRequest which performs atomic move operations.
    Accepts single path (str) or multiple paths (list[str]) for source_paths.
    Supports glob patterns (e.g., "/path/to/*.txt") for matching multiple files.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add moved_paths output parameter (copied_paths_output from parent will remain but won't be used)
        self.moved_paths_output = Parameter(
            name="moved_paths",
            allow_input=False,
            allow_property=False,
            output_type="list[str]",
            default_value=[],
            tooltip="List of all destination paths that were moved successfully.",
        )
        self.add_parameter(self.moved_paths_output)

        # Update tooltips to say "move" instead of "copy"
        self.source_paths.tooltip = (
            "Path(s) to file(s) or directory(ies) to move. Supports glob patterns (e.g., '/path/*.txt')."
        )
        self.destination_path.tooltip = "Destination directory where files will be moved."

    def _execute_move(self, target: MoveFileInfo, destination_dir: str, *, overwrite: bool) -> None:
        """Execute move operation for a single target using RenameFileRequest.

        Args:
            target: MoveFileInfo with source_path set
            destination_dir: Destination directory
            overwrite: Whether to overwrite existing files
        """
        # Resolve destination path
        destination_path = self._resolve_destination_path(target.source_path, destination_dir)
        target.destination_path = destination_path

        # If overwrite is True and destination exists, delete it first
        if overwrite:
            dest_info_request = GetFileInfoRequest(path=destination_path, workspace_only=False)
            dest_info_result = GriptapeNodes.handle_request(dest_info_request)

            if isinstance(dest_info_result, GetFileInfoResultSuccess) and dest_info_result.file_entry is not None:
                # Destination exists - delete it first
                delete_request = DeleteFileRequest(path=destination_path, workspace_only=False)
                delete_result = GriptapeNodes.handle_request(delete_request)

                if isinstance(delete_result, DeleteFileResultFailure):
                    target.status = MoveStatus.FAILED
                    target.failure_reason = (
                        f"Failed to delete existing destination: {delete_result.failure_reason.value}"
                    )
                    return

        # Execute move using RenameFileRequest (which performs atomic move)
        rename_request = RenameFileRequest(
            old_path=target.source_path,
            new_path=destination_path,
            workspace_only=False,
        )
        rename_result = GriptapeNodes.handle_request(rename_request)

        if isinstance(rename_result, RenameFileResultFailure):
            target.status = MoveStatus.FAILED
            target.failure_reason = f"Move failed: {rename_result.failure_reason.value}"
            return

        # SUCCESS PATH AT END - result must be RenameFileResultSuccess (only two possible types)
        success_result = cast("RenameFileResultSuccess", rename_result)
        target.status = MoveStatus.SUCCESS
        target.moved_paths = [success_result.new_path]

    def _format_result_details(self, all_targets: list[MoveFileInfo]) -> str:
        """Format detailed results showing what happened to each file."""
        lines = []

        # Count outcomes
        succeeded = [t for t in all_targets if t.status == MoveStatus.SUCCESS]
        failed = [t for t in all_targets if t.status == MoveStatus.FAILED]
        invalid = [t for t in all_targets if t.status == MoveStatus.INVALID]

        # Summary line
        valid_targets = [t for t in all_targets if t.status != MoveStatus.INVALID]
        lines.append(f"Moved {len(succeeded)}/{len(valid_targets)} valid items")

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

        # Handle empty paths as success with info message (consistent with delete_file)
        if not source_paths_raw:
            msg = "No files specified for moving"
            self.set_parameter_value(self.moved_paths_output.name, [])
            self._set_status_results(was_successful=True, result_details=msg)
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
        all_targets = self._collect_all_files(
            paths=source_paths,
            info_class=MoveFileInfo,
            pending_status=MoveStatus.PENDING,
            invalid_status=MoveStatus.INVALID,
        )

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
        # Consider it successful if at least one file was moved
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
