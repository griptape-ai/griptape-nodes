from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    DeleteFileResultFailure,
    DeleteFileResultSuccess,
    GetFileInfoRequest,
    GetFileInfoResultFailure,
    GetFileInfoResultSuccess,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class DeletionStatus(Enum):
    """Status of a deletion attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # Skipped because parent directory was deleted
    INVALID = "invalid"  # Invalid or inaccessible path


@dataclass
class DeleteFileInfo:
    """Information about a file/directory deletion attempt."""

    path: str  # Workspace-relative path (for portability)
    is_directory: bool
    absolute_path: str  # Absolute resolved path
    status: DeletionStatus = DeletionStatus.PENDING
    failure_reason: str | None = None
    deleted_paths: list[str] = field(default_factory=list)  # Paths actually deleted (from OS result)
    explicitly_requested: bool = False  # True if user specified this path, False if discovered via recursion


class DeleteFile(SuccessFailureNode):
    """Delete files and/or directories from the file system.

    Directories are deleted with all their contents.
    Accepts single path (str) or multiple paths (list[str]).
    Supports glob patterns (e.g., "/path/to/*.txt") for matching multiple files.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Input parameter - accepts str or list[str]
        self.file_paths = ParameterList(
            name="paths",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "list"],
            default_value=None,
            tooltip="Paths to files or directories to delete. Supports glob patterns (e.g., '/path/*.txt').",
            traits={
                FileSystemPicker(
                    allow_files=True,
                    allow_directories=True,
                    multiple=True,
                )
            },
        )
        self.add_parameter(self.file_paths)

        # Warning message (always visible)
        self.deletion_warning = ParameterMessage(
            variant="warning",
            value="⚠️ Destructive Operation: This node permanently deletes files and directories. Deleted items cannot be recovered.",
            name="deletion_warning",
        )
        self.add_node_element(self.deletion_warning)

        # Output parameter
        self.deleted_paths_output = Parameter(
            name="deleted_paths",
            allow_input=False,
            allow_property=False,
            output_type="list[str]",
            default_value=[],
            tooltip="List of all paths that were deleted.",
        )
        self.add_parameter(self.deleted_paths_output)

        # Create status parameters (initially expanded)
        self._create_status_parameters(
            result_details_tooltip="Details about the deletion result",
            result_details_placeholder="Details on the deletion attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

    def _normalize_paths_input(self, value: Any) -> list[str]:
        """Normalize input to list of path strings."""
        if isinstance(value, str):
            if not value:
                return []
            return [value]
        if isinstance(value, list):
            return [str(p) for p in value if p]
        return []

    def _is_glob_pattern(self, path_str: str) -> bool:
        """Check if a path string contains glob pattern characters."""
        return any(char in path_str for char in ["*", "?", "[", "]"])

    def _expand_glob_pattern(self, path_str: str, all_targets: list[DeleteFileInfo]) -> None:
        """Expand a glob pattern using ListDirectoryRequest and add matches to all_targets.

        Args:
            path_str: Glob pattern (e.g., "/path/to/*.txt")
            all_targets: List to append matching DeleteFileInfo entries to
        """
        # Parse the pattern into directory and pattern parts
        path = Path(path_str)

        # If the pattern has multiple parts with wildcards, we need to handle parent resolution
        # For now, we'll support patterns where only the last component has wildcards
        # e.g., "/path/to/*.txt" or "/path/to/file*.json"
        if self._is_glob_pattern(str(path.parent)):
            # Parent directory contains wildcards - this is more complex, treat as invalid
            all_targets.append(
                DeleteFileInfo(
                    path=path_str,
                    is_directory=False,
                    absolute_path=path_str,
                    status=DeletionStatus.INVALID,
                    failure_reason="Glob patterns in parent directories are not supported",
                )
            )
            return

        # Directory is the parent, pattern is the name with wildcards
        directory_path = str(path.parent)
        pattern = path.name

        # Use ListDirectoryRequest with pattern matching
        request = ListDirectoryRequest(
            directory_path=directory_path, show_hidden=True, workspace_only=False, pattern=pattern
        )
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ListDirectoryResultSuccess):
            if not result.entries:
                # No matches found - treat as invalid
                all_targets.append(
                    DeleteFileInfo(
                        path=path_str,
                        is_directory=False,
                        absolute_path=path_str,
                        status=DeletionStatus.INVALID,
                        failure_reason=f"No files match pattern '{pattern}'",
                    )
                )
            else:
                # Add all matching entries as PENDING (explicitly requested via glob pattern)
                all_targets.extend(
                    DeleteFileInfo(
                        path=entry.path,
                        is_directory=entry.is_dir,
                        status=DeletionStatus.PENDING,
                        explicitly_requested=True,
                        absolute_path=entry.absolute_path,
                    )
                    for entry in result.entries
                )
        else:
            # Directory doesn't exist or can't be accessed
            failure_msg = (
                result.failure_reason.value if isinstance(result, ListDirectoryResultFailure) else "Unknown error"
            )
            all_targets.append(
                DeleteFileInfo(
                    path=path_str,
                    is_directory=False,
                    absolute_path=path_str,
                    status=DeletionStatus.INVALID,
                    failure_reason=failure_msg,
                )
            )

    def _list_directory_recursively(self, dir_path: str, targets: list[DeleteFileInfo]) -> None:
        """Recursively list all files in a directory and add to targets."""
        request = ListDirectoryRequest(directory_path=dir_path, show_hidden=True, workspace_only=False)
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ListDirectoryResultSuccess):
            for entry in result.entries:
                # Add this entry with PENDING status
                targets.append(
                    DeleteFileInfo(
                        path=entry.path,
                        is_directory=entry.is_dir,
                        absolute_path=entry.absolute_path,
                        status=DeletionStatus.PENDING,
                    )
                )

                # If it's a directory, recurse into it
                if entry.is_dir:
                    self._list_directory_recursively(entry.path, targets)

    def _collect_all_deletion_targets(self, paths: list[str]) -> list[DeleteFileInfo]:
        """Collect all files/directories that will be deleted.

        Handles both explicit paths and glob patterns (e.g., "/path/to/*.txt").
        Glob patterns match individual files in a directory, not subdirectories.

        Returns:
            List of DeleteFileInfo with status set (PENDING for valid paths, INVALID for invalid paths)
        """
        all_targets: list[DeleteFileInfo] = []

        for path_str in paths:
            # Check if this is a glob pattern
            if self._is_glob_pattern(path_str):
                # Expand the pattern using ListDirectoryRequest
                self._expand_glob_pattern(path_str, all_targets)
                continue

            # Not a glob pattern - handle as explicit path
            # Get file info for this path (OS manager handles path resolution)
            request = GetFileInfoRequest(path=path_str, workspace_only=False)
            result = GriptapeNodes.handle_request(request)

            if isinstance(result, GetFileInfoResultSuccess):
                file_entry = result.file_entry

                # Add the root item with PENDING status (explicitly requested by user)
                all_targets.append(
                    DeleteFileInfo(
                        path=file_entry.path,
                        is_directory=file_entry.is_dir,
                        absolute_path=file_entry.absolute_path,
                        status=DeletionStatus.PENDING,
                        explicitly_requested=True,
                    )
                )

                # If it's a directory, recursively get ALL contents for the WARNING display only
                # These children will NOT be deleted individually - they'll be deleted when the parent is deleted
                if file_entry.is_dir:
                    self._list_directory_recursively(file_entry.path, all_targets)
            else:
                # Path doesn't exist or can't be accessed - add with INVALID status
                failure_msg = (
                    result.failure_reason.value if isinstance(result, GetFileInfoResultFailure) else "Unknown error"
                )
                all_targets.append(
                    DeleteFileInfo(
                        path=path_str,
                        is_directory=False,
                        absolute_path=path_str,
                        status=DeletionStatus.INVALID,
                        failure_reason=failure_msg,
                    )
                )

        # Deduplicate by absolute_path
        # If same path appears multiple times, prefer the one with explicitly_requested=True
        unique_targets: dict[str, DeleteFileInfo] = {}
        for target in all_targets:
            if target.absolute_path not in unique_targets:
                unique_targets[target.absolute_path] = target
            elif target.explicitly_requested and not unique_targets[target.absolute_path].explicitly_requested:
                # Replace with the explicitly requested version
                unique_targets[target.absolute_path] = target

        return list(unique_targets.values())

    def _format_deletion_warning(self, all_targets: list[DeleteFileInfo]) -> str:
        """Format warning message with all files sorted by directory."""
        lines = []

        # Separate invalid and valid targets
        invalid_targets = [t for t in all_targets if t.status == DeletionStatus.INVALID]
        valid_targets = [t for t in all_targets if t.status == DeletionStatus.PENDING]

        # Show invalid paths first if any
        if invalid_targets:
            lines.append("⚠️ Invalid or inaccessible paths:")
            lines.append("")
            for target in sorted(invalid_targets, key=lambda t: t.path):
                reason = f" ({target.failure_reason})" if target.failure_reason else ""
                lines.append(f"  ❌ {target.path}{reason}")
            lines.append("")

        # Show valid files to be deleted
        if valid_targets:
            if invalid_targets:
                lines.append("---")
                lines.append("")
            lines.append("You are about to delete the following files and directories:")
            lines.append("")

            # Sort paths by directory structure
            sorted_targets = sorted(valid_targets, key=lambda t: (Path(t.path).parent, Path(t.path).name))

            # Group by parent directory for better readability
            current_parent = None
            for target in sorted_targets:
                path = Path(target.path)
                parent = path.parent

                if parent != current_parent:
                    if current_parent is not None:
                        lines.append("")  # Empty line between directories
                    lines.append(f"{parent}/")
                    current_parent = parent

                # Indent file names under their parent
                if target.is_directory:
                    lines.append(f"  📁 {path.name}/")
                else:
                    lines.append(f"  📄 {path.name}")

            lines.append("")
            lines.append(f"Total: {len(valid_targets)} items will be deleted")

        # If nothing valid, just show that
        if not valid_targets and not invalid_targets:
            return "No valid paths provided"

        return "\n".join(lines)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Override to clear state when connection to file_paths is removed."""
        # If connection to file_paths was removed, reset the warning
        if target_parameter is self.file_paths:
            # Clear the parameter value and reset warning
            self.file_paths.clear_list()

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to update deletion warning when file_paths changes."""
        # Call parent implementation first
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        # Update warning if file_paths changed
        if param_name == self.file_paths.name:
            # Normalize input to list
            paths = self.get_parameter_list_value(self.file_paths.name)

            if paths:
                # Collect all files/directories that will be deleted
                all_targets = self._collect_all_deletion_targets(paths)

                # Update warning with detailed file list
                warning_text = self._format_deletion_warning(all_targets)
                self.deletion_warning.value = warning_text
            else:
                # Reset to default warning when no paths specified
                self.deletion_warning.value = "⚠️ Destructive Operation: This node permanently deletes files and directories. Deleted items cannot be recovered."

    def _execute_deletions(self, deletion_order: list[DeleteFileInfo]) -> tuple[list[str], list[Path]]:
        """Execute deletions and track results.

        Args:
            deletion_order: List of targets to delete in order

        Returns:
            Tuple of (deleted_paths_str, deleted_paths_pathobj) for tracking
        """
        all_deleted_paths_str: list[str] = []
        all_deleted_paths_pathobj: list[Path] = []

        for target in deletion_order:
            # Skip if this path was already deleted as part of a parent directory
            target_path = Path(target.path)
            if any(deleted_parent in target_path.parents for deleted_parent in all_deleted_paths_pathobj):
                target.status = DeletionStatus.SKIPPED
                continue

            # Create and send delete request
            request = DeleteFileRequest(path=target.path, workspace_only=False)
            result = GriptapeNodes.handle_request(request)

            if isinstance(result, DeleteFileResultFailure):
                # Track failure but continue
                target.status = DeletionStatus.FAILED
                target.failure_reason = result.failure_reason.value
            elif isinstance(result, DeleteFileResultSuccess):
                # Track success
                target.status = DeletionStatus.SUCCESS
                target.deleted_paths = result.deleted_paths
                all_deleted_paths_str.extend(result.deleted_paths)
                all_deleted_paths_pathobj.extend(Path(p) for p in result.deleted_paths)
            else:
                # Unexpected result type - track as failure
                target.status = DeletionStatus.FAILED
                target.failure_reason = "Unexpected result type from delete operation"

        return all_deleted_paths_str, all_deleted_paths_pathobj

    def _format_result_details(self, all_targets: list[DeleteFileInfo]) -> str:
        """Format detailed results showing what happened to each file."""
        lines = []

        # Count outcomes
        succeeded = [t for t in all_targets if t.status == DeletionStatus.SUCCESS]
        failed = [t for t in all_targets if t.status == DeletionStatus.FAILED]
        invalid = [t for t in all_targets if t.status == DeletionStatus.INVALID]
        skipped = [t for t in all_targets if t.status == DeletionStatus.SKIPPED]

        # Summary line
        lines.append(
            f"Deleted {len(succeeded)}/{len([t for t in all_targets if t.status != DeletionStatus.INVALID])} valid items"
        )

        # Show failures if any
        if failed:
            lines.append(f"\nFailed to delete ({len(failed)}):")
            for target in failed:
                reason = target.failure_reason or "Unknown error"
                lines.append(f"  ❌ {target.path}: {reason}")

        # Show invalid paths if any
        if invalid:
            lines.append(f"\nInvalid paths ({len(invalid)}):")
            for target in invalid:
                reason = target.failure_reason or "Invalid or inaccessible"
                lines.append(f"  ⚠️ {target.path}: {reason}")

        # Show skipped if any
        if skipped:
            max_skipped_to_show = 5
            lines.append(f"\nSkipped (parent directory deleted) ({len(skipped)}):")
            lines.extend(f"  ⏭️ {target.path}" for target in skipped[:max_skipped_to_show])
            if len(skipped) > max_skipped_to_show:
                lines.append(f"  ... and {len(skipped) - max_skipped_to_show} more")

        return "\n".join(lines)

    def process(self) -> None:
        """Execute the file deletion."""
        self._clear_execution_status()

        # Get parameter value
        paths = self.get_parameter_list_value(self.file_paths.name)

        # FAILURE CASE: Empty paths
        if not paths:
            msg = f"{self.name} attempted to delete with empty paths. Failed due to no paths provided"
            self.set_parameter_value(self.deleted_paths_output.name, None)
            self._set_status_results(was_successful=False, result_details=msg)
            return

        # Collect all targets (includes INVALID status for bad paths)
        all_targets = self._collect_all_deletion_targets(paths)

        # Separate valid and invalid targets
        pending_targets = [t for t in all_targets if t.status == DeletionStatus.PENDING]

        # FAILURE CASE: No valid targets at all
        if not pending_targets:
            msg = f"{self.name} attempted to delete but all paths were invalid. No files deleted"
            details = self._format_result_details(all_targets)
            self.set_parameter_value(self.deleted_paths_output.name, None)
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # Only delete explicitly requested items
        # Children are included in all_targets for WARNING display, but deleting a directory deletes its contents
        explicitly_requested = [t for t in pending_targets if t.explicitly_requested]

        # Sort deletion order: files first (deepest first), then directories (deepest first)
        files = [t for t in explicitly_requested if not t.is_directory]
        directories = [t for t in explicitly_requested if t.is_directory]

        # Use Path.parts for cross-platform depth calculation (works on Windows and Unix)
        sorted_files = sorted(files, key=lambda t: len(Path(t.path).parts), reverse=True)
        sorted_directories = sorted(directories, key=lambda t: len(Path(t.path).parts), reverse=True)

        # Delete in order: files first, then directories
        deletion_order = sorted_files + sorted_directories

        # Execute deletions and track results
        all_deleted_paths_str = self._execute_deletions(deletion_order)[0]

        # Only report on explicitly requested items (not children discovered via recursion)
        requested_targets = [t for t in all_targets if t.explicitly_requested]

        # Determine success/failure
        succeeded_count = len([t for t in requested_targets if t.status == DeletionStatus.SUCCESS])

        # FAILURE CASE: Zero files were successfully deleted
        if succeeded_count == 0:
            msg = f"{self.name} failed to delete any files"
            details = self._format_result_details(requested_targets)
            self.set_parameter_value(self.deleted_paths_output.name, None)
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            return

        # SUCCESS PATH AT END (even if some failed, as long as at least one succeeded)
        # Set output parameters
        self.set_parameter_value(self.deleted_paths_output.name, all_deleted_paths_str)
        self.parameter_output_values[self.deleted_paths_output.name] = all_deleted_paths_str

        # Generate detailed result message (only for explicitly requested items)
        details = self._format_result_details(requested_targets)

        self._set_status_results(was_successful=True, result_details=details)
