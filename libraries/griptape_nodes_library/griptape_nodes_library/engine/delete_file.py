from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    NodeMessageResult,
    Parameter,
    ParameterList,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
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
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload

# Default warning message for destructive operation
DEFAULT_DELETION_WARNING = (
    "⚠️ Destructive Operation: This node permanently deletes files and directories. Deleted items cannot be recovered."
)

# Maximum number of files to list in the warning display before truncating
MAX_FILES_TO_DISPLAY = 50


class DeletionStatus(Enum):
    """Status of a deletion attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
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

    # Track if file listing was truncated for display
    _listing_truncated: bool = False

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Input parameter - accepts str or list[str]
        self.file_paths = ParameterList(
            name="file_paths",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "list"],
            default_value=None,
            tooltip="Paths to files or directories to delete. Supports glob patterns (e.g., '/path/*.txt').",
        )
        self.add_parameter(self.file_paths)

        # Output parameter
        self.deleted_paths_output = Parameter(
            name="deleted_paths",
            allow_input=False,
            allow_property=False,
            output_type="list",
            default_value=[],
            tooltip="List of all paths that were deleted.",
        )
        self.add_parameter(self.deleted_paths_output)

        # Warning message (always visible) with refresh button
        self.deletion_warning = ParameterMessage(
            variant="warning",
            value=DEFAULT_DELETION_WARNING,
            name="deletion_warning",
            button_text="Refresh List",
            button_variant="secondary",
            traits={
                Button(
                    label="Refresh List",
                    icon="refresh-cw",
                    variant="secondary",
                    tooltip="Re-scan the file system to update the deletion list",
                    on_click=self._refresh_deletion_list,
                )
            },
        )
        self.add_node_element(self.deletion_warning)

        # Create status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the deletion result",
            result_details_placeholder="Details on the deletion attempt will be presented here.",
            parameter_group_initially_collapsed=True,
        )

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
            # Reset variant to warning when parameters change
            self.deletion_warning.variant = "warning"

            # Normalize input to list
            param_values = self.get_parameter_list_value(self.file_paths.name)
            # Dupe strip
            paths = set(param_values)

            if paths:
                # Collect all files/directories that will be deleted
                all_targets = self._collect_all_deletion_targets(paths)

                # Update warning with detailed file list
                warning_text = self._format_deletion_warning(all_targets)
                self.deletion_warning.value = warning_text
            else:
                # Reset to default warning when no paths specified
                self.deletion_warning.value = DEFAULT_DELETION_WARNING

    def process(self) -> None:
        """Execute the file deletion."""
        self._clear_execution_status()

        # Get paths from param list.
        param_values = self.get_parameter_list_value(self.file_paths.name)
        # Dupe strip
        paths = set(param_values)

        # Handle empty paths as success with info message
        if not paths:
            msg = "No files specified for deletion"
            self.set_parameter_value(self.deleted_paths_output.name, [])
            self._set_status_results(was_successful=True, result_details=msg)
            # Update warning message with info
            self.deletion_warning.variant = "info"
            self.deletion_warning.value = msg
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
            # Update warning message with error
            self.deletion_warning.variant = "error"
            self.deletion_warning.value = details
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
        all_deleted_paths = self._execute_deletions(deletion_order)

        # For summary counts, only count explicitly requested items
        requested_targets = [t for t in all_targets if t.explicitly_requested]
        succeeded_count = len([t for t in requested_targets if t.status == DeletionStatus.SUCCESS])

        # FAILURE CASE: Zero files were successfully deleted
        if succeeded_count == 0:
            msg = f"{self.name} failed to delete any files"
            # Show all targets in details (including children)
            details = self._format_result_details(all_targets)
            self.set_parameter_value(self.deleted_paths_output.name, None)
            self._set_status_results(was_successful=False, result_details=f"{msg}\n\n{details}")
            # Update warning message with error
            self.deletion_warning.variant = "error"
            self.deletion_warning.value = details
            return

        # SUCCESS PATH AT END (even if some failed, as long as at least one succeeded)
        # Set output parameters
        self.set_parameter_value(self.deleted_paths_output.name, all_deleted_paths)
        self.parameter_output_values[self.deleted_paths_output.name] = all_deleted_paths

        # Generate detailed result message showing all targets (including children)
        details = self._format_result_details(all_targets)

        self._set_status_results(was_successful=True, result_details=details)

        # Update warning message with results
        # Determine variant: success if no problems, error if there were failures or invalid paths
        failed_count = len([t for t in all_targets if t.status == DeletionStatus.FAILED])
        invalid_count = len([t for t in all_targets if t.status == DeletionStatus.INVALID])

        if failed_count > 0 or invalid_count > 0:
            self.deletion_warning.variant = "error"
        else:
            self.deletion_warning.variant = "success"

        self.deletion_warning.value = details

    def _refresh_deletion_list(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult:
        """Refresh the deletion list by re-scanning the file system.

        Called when the user clicks the Refresh List button.
        """
        # Get current file paths
        param_values = self.get_parameter_list_value(self.file_paths.name)
        # Dupe strip
        paths = set(param_values)

        if paths:
            # Re-scan file system
            all_targets = self._collect_all_deletion_targets(paths)

            # Update warning message with fresh results
            warning_text = self._format_deletion_warning(all_targets)
            self.deletion_warning.value = warning_text

            return NodeMessageResult(
                success=True,
                details="File list refreshed successfully",
                response=button_details,
            )

        # No paths to refresh
        return NodeMessageResult(
            success=True,
            details="No file paths provided",
            response=button_details,
        )

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

    def _list_directory_recursively(self, dir_path: str, targets: list[DeleteFileInfo]) -> bool:
        """Recursively list all files in a directory and add to targets.

        Returns:
            True if limit reached, False otherwise
        """
        # Check if we've hit the display limit
        if len(targets) >= MAX_FILES_TO_DISPLAY:
            return True

        request = ListDirectoryRequest(directory_path=dir_path, show_hidden=True, workspace_only=False)
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ListDirectoryResultSuccess):
            for entry in result.entries:
                # Check limit before adding each entry
                if len(targets) >= MAX_FILES_TO_DISPLAY:
                    return True

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
                    limit_reached = self._list_directory_recursively(entry.path, targets)
                    if limit_reached:
                        return True
        elif isinstance(result, ListDirectoryResultFailure):
            # Failed to list directory (permission denied, doesn't exist, etc.)
            # Add as INVALID and stop recursion into this directory
            targets.append(
                DeleteFileInfo(
                    path=dir_path,
                    is_directory=True,
                    absolute_path=dir_path,
                    status=DeletionStatus.INVALID,
                    failure_reason=result.failure_reason.value,
                )
            )

        return False

    def _collect_all_deletion_targets(self, paths: set[str]) -> list[DeleteFileInfo]:
        """Collect all files/directories that will be deleted.

        Handles both explicit paths and glob patterns (e.g., "/path/to/*.txt").
        Glob patterns match individual files in a directory, not subdirectories.

        Returns:
            Set of DeleteFileInfo with status set (PENDING for valid paths, INVALID for invalid paths)
        """
        # Reset truncation flag
        self._listing_truncated = False
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

                # Check if file_entry is None (file doesn't exist)
                if file_entry is None:
                    # File doesn't exist - add with INVALID status
                    all_targets.append(
                        DeleteFileInfo(
                            path=path_str,
                            is_directory=False,
                            absolute_path=path_str,
                            status=DeletionStatus.INVALID,
                            failure_reason="File or directory does not exist",
                        )
                    )
                else:
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
                        limit_reached = self._list_directory_recursively(file_entry.path, all_targets)
                        if limit_reached:
                            # Mark that listing was truncated
                            self._listing_truncated = True
            else:
                # Request failed (permission error, I/O error, etc.) - add with INVALID status
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

    def _format_deletion_warning(self, all_targets: list[DeleteFileInfo]) -> str:  # noqa: C901, PLR0912
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

            # Show truncation message if listing was truncated
            if self._listing_truncated:
                lines.append(f"... (listing truncated after {MAX_FILES_TO_DISPLAY} files)")
                lines.append("")

            # Show total count - indicate if truncated
            if self._listing_truncated:
                lines.append(f"More than {len(valid_targets)} items will be deleted")
            else:
                lines.append(f"Total: {len(valid_targets)} items will be deleted")

        # If nothing valid, just show that
        if not valid_targets and not invalid_targets:
            return "No valid paths provided"

        return "\n".join(lines)

    def _execute_deletions(self, deletion_order: list[DeleteFileInfo]) -> list[str]:
        """Execute deletions and track results.

        Args:
            deletion_order: List of targets to delete in order

        Returns:
            List of all paths that were successfully deleted (as strings)
        """
        all_deleted_paths: list[str] = []

        for target in deletion_order:
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
                all_deleted_paths.extend(result.deleted_paths)
            else:
                # Unexpected result type - track as failure
                target.status = DeletionStatus.FAILED
                target.failure_reason = "Unexpected result type from delete operation"

        return all_deleted_paths

    def _format_result_details(self, all_targets: list[DeleteFileInfo]) -> str:
        """Format detailed results showing what happened to each file."""
        lines = []

        # Count outcomes
        succeeded = [t for t in all_targets if t.status == DeletionStatus.SUCCESS]
        failed = [t for t in all_targets if t.status == DeletionStatus.FAILED]
        invalid = [t for t in all_targets if t.status == DeletionStatus.INVALID]

        # Summary line - only count explicitly requested items
        valid_requested = [t for t in all_targets if t.explicitly_requested and t.status != DeletionStatus.INVALID]
        lines.append(f"Deleted {len(succeeded)}/{len(valid_requested)} items")

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

        # Show successfully deleted files
        if succeeded:
            lines.append(f"\nSuccessfully deleted ({len(succeeded)}):")
            for target in succeeded:
                if target.is_directory:
                    lines.append(f"  📁 {target.path}")
                else:
                    lines.append(f"  📄 {target.path}")

        return "\n".join(lines)
