from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar
from urllib.parse import urlparse

from griptape.artifacts import UrlArtifact

from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.os_events import (
    GetFileInfoRequest,
    GetFileInfoResultFailure,
    GetFileInfoResultSuccess,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import Enum

    from griptape_nodes.exe_types.core_types import Parameter

# TypeVar for file operation Info types
T = TypeVar("T", bound="FileOperationInfo")


class FileOperationInfo(Protocol):
    """Protocol defining the interface for file operation Info types."""

    source_path: str
    explicitly_requested: bool


@dataclass
class BaseFileOperationInfo:
    """Base dataclass for file operation Info types.

    Provides common fields shared by CopyFileInfo, MoveFileInfo, etc.
    Subclasses should add operation-specific fields like status enum and result paths.
    """

    source_path: str  # Workspace-relative path
    destination_path: str  # Destination path
    is_directory: bool
    failure_reason: str | None = None
    explicitly_requested: bool = False


@dataclass
class PathExistsResult:
    """Result of checking if a path exists."""

    exists: bool
    is_directory: bool


class FileOperationBaseNode(SuccessFailureNode):
    """Base class for file operation nodes (copy, move, rename, etc.).

    Provides common functionality for:
    - Resolving localhost URLs to workspace paths
    - Extracting values from artifacts
    - Checking if paths exist
    - Glob pattern detection
    """

    def _resolve_localhost_url_to_path(self, url: str) -> str:
        """Resolve localhost static file URLs to workspace file paths.

        Converts URLs like http://localhost:8124/workspace/static_files/file.jpg
        to actual workspace file paths like static_files/file.jpg

        Args:
            url: URL string that may be a localhost URL

        Returns:
            Resolved file path relative to workspace, or original string if not a localhost URL
        """
        if not isinstance(url, str):
            return url

        # Strip query parameters (cachebuster ?t=...)
        if "?" in url:
            url = url.split("?")[0]

        # Check if it's a localhost URL (any port)
        if url.startswith(("http://localhost:", "https://localhost:")):
            parsed = urlparse(url)
            # Extract path after /workspace/
            if "/workspace/" in parsed.path:
                workspace_relative_path = parsed.path.split("/workspace/", 1)[1]
                return workspace_relative_path

        # Not a localhost workspace URL, return as-is
        return url

    def _extract_value_from_artifact(self, value: Any) -> str:  # noqa: PLR0911
        """Extract string value from artifact objects, dicts, or strings.

        Also resolves localhost URLs to workspace paths.

        Args:
            value: Artifact object, dict with "value" key, or string

        Returns:
            String value extracted from the artifact, with URLs resolved
        """
        if isinstance(value, str):
            # Resolve localhost URLs to workspace paths
            return self._resolve_localhost_url_to_path(value)

        if isinstance(value, dict):
            extracted = str(value.get("value", value))
            # Resolve URLs if it's a string
            if isinstance(extracted, str):
                return self._resolve_localhost_url_to_path(extracted)
            return extracted

        if isinstance(value, UrlArtifact):
            extracted = str(value.value)
            # Resolve URLs
            return self._resolve_localhost_url_to_path(extracted)

        if hasattr(value, "value"):
            extracted = str(value.value)
            # Resolve URLs if it's a string
            if isinstance(extracted, str):
                return self._resolve_localhost_url_to_path(extracted)
            return extracted

        return str(value)

    def _extract_artifacts_from_value(self, value: Any) -> Any:
        """Recursively extract artifact values from nested structures.

        Args:
            value: Value that may contain artifacts, lists, or nested structures

        Returns:
            Value with artifacts extracted to strings
        """
        if value is None:
            return None

        if isinstance(value, str):
            # Resolve localhost URLs to workspace paths
            return self._resolve_localhost_url_to_path(value)

        if isinstance(value, list):
            return [self._extract_artifacts_from_value(item) for item in value]

        # Extract from artifact, then resolve URL if needed
        extracted = self._extract_value_from_artifact(value)
        if isinstance(extracted, str):
            return self._resolve_localhost_url_to_path(extracted)
        return extracted

    def _is_glob_pattern(self, path_str: str) -> bool:
        """Check if a path string contains glob pattern characters.

        Args:
            path_str: Path string to check

        Returns:
            True if path contains glob pattern characters (*, ?, [, ])
        """
        return any(char in path_str for char in ["*", "?", "[", "]"])

    def _check_path_exists(self, path: str) -> PathExistsResult:
        """Check if a path exists and whether it's a directory.

        Args:
            path: Path to check

        Returns:
            PathExistsResult with exists and is_directory flags
        """
        request = GetFileInfoRequest(path=path, workspace_only=False)
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, GetFileInfoResultFailure):
            return PathExistsResult(exists=False, is_directory=False)

        if isinstance(result, GetFileInfoResultSuccess):
            if result.file_entry is None:
                # File doesn't exist
                return PathExistsResult(exists=False, is_directory=False)
            # File exists - return its directory status
            return PathExistsResult(exists=True, is_directory=result.file_entry.is_dir)

        # Unexpected result type
        return PathExistsResult(exists=False, is_directory=False)

    def _resolve_destination_path(self, source_path: str, destination_dir: str) -> str:
        """Resolve the full destination path for a source file/directory.

        If destination_dir looks like a file path (has an extension or ends with a filename),
        use it as-is. Otherwise, treat it as a directory and append the source filename.

        Args:
            source_path: Source file/directory path
            destination_dir: Destination directory path or full destination file path

        Returns:
            Full destination path
        """
        destination_path_obj = Path(destination_dir)

        # Check if destination_dir looks like a file path (has an extension)
        if destination_path_obj.suffix:
            # Has an extension - treat as file path, use as-is
            return str(destination_path_obj)

        # Check if destination exists and is a directory
        # If it doesn't exist, we'll treat it as a directory and let CopyFileRequest create it
        dest_info_request = GetFileInfoRequest(path=destination_dir, workspace_only=False)
        dest_info_result = GriptapeNodes.handle_request(dest_info_request)

        if (
            isinstance(dest_info_result, GetFileInfoResultSuccess)
            and dest_info_result.file_entry is not None
            and dest_info_result.file_entry.is_dir
        ):
            # It's a directory - append source filename
            source_name = Path(source_path).name
            return str(destination_path_obj / source_name)

        # Destination doesn't exist or isn't a directory - treat it as a directory
        # CopyFileRequest/CopyTreeRequest will create parent directories as needed
        # This handles the case where the destination directory doesn't exist yet
        source_name = Path(source_path).name
        return str(destination_path_obj / source_name)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle artifact extraction after value is set.

        This ensures that when artifacts are connected to ParameterList children,
        their values are properly extracted and displayed in the UI.
        """
        # Only process source_paths ParameterList and its children
        is_source_paths = parameter.name == "source_paths"
        is_child_of_source_paths = (
            hasattr(parameter, "parent_container_name") and parameter.parent_container_name == "source_paths"
        )

        if (is_source_paths or is_child_of_source_paths) and value is not None:
            # Extract artifact values if needed
            extracted = self._extract_artifacts_from_value(value)
            # If extraction changed the value, update it
            if extracted != value:
                # Update the parameter value directly
                if parameter.name in self.parameter_values:
                    self.parameter_values[parameter.name] = extracted
                # Also update the child parameter if it's a child
                if is_child_of_source_paths:
                    # The value is already set, but we need to trigger UI update
                    self.publish_update_to_parameter(parameter.name, extracted)

        super().after_value_set(parameter, value)

    def _collect_all_targets(
        self,
        paths: list[str],
        all_targets: list[T],
        create_pending_info: Callable[..., T],  # (source_path: str, destination_path: str, *, is_directory: bool) -> T
        create_invalid_info: Callable[[str, str], T],
        expand_glob_pattern: Callable[[str, list[T]], None],
    ) -> list[T]:
        """Collect all files/directories that will be operated on.

        Handles both explicit paths and glob patterns (e.g., "/path/to/*.txt").
        Glob patterns match individual files in a directory, not subdirectories.

        Args:
            paths: List of path strings to process
            all_targets: List to append Info objects to
            create_pending_info: Factory function to create Info object with PENDING status
            create_invalid_info: Factory function to create Info object with INVALID status
            expand_glob_pattern: Function to expand glob patterns and add matches to all_targets

        Returns:
            List of Info objects with status set (PENDING for valid paths, INVALID for invalid paths)
        """
        for path_str in paths:
            # Check if this is a glob pattern
            if self._is_glob_pattern(path_str):
                # Expand the pattern using the provided function
                expand_glob_pattern(path_str, all_targets)
                continue

            # Not a glob pattern - handle as explicit path
            # Get file info for this path (OS manager handles path resolution)
            request = GetFileInfoRequest(path=path_str, workspace_only=False)
            result = GriptapeNodes.handle_request(request)

            if isinstance(result, GetFileInfoResultSuccess):
                file_entry = result.file_entry

                # Check if file_entry is None (file doesn't exist)
                if file_entry is None:
                    # Path doesn't exist
                    all_targets.append(
                        create_invalid_info(
                            path_str,
                            "File or directory not found",
                        )
                    )
                else:
                    # Add the root item with PENDING status (explicitly requested by user)
                    all_targets.append(
                        create_pending_info(
                            file_entry.path,
                            "",  # Will be set during operation
                            is_directory=file_entry.is_dir,
                        )
                    )
            else:
                # Request failed (permission error, I/O error, etc.)
                failure_msg = (
                    result.failure_reason.value if isinstance(result, GetFileInfoResultFailure) else "Unknown error"
                )
                all_targets.append(
                    create_invalid_info(
                        path_str,
                        failure_msg,
                    )
                )

        # Deduplicate by source_path
        # If same path appears multiple times, prefer the one with explicitly_requested=True
        unique_targets: dict[str, T] = {}
        for target in all_targets:
            # Access source_path attribute (all Info types have this)
            source_path = target.source_path
            if source_path not in unique_targets:
                unique_targets[source_path] = target
            else:
                # Access explicitly_requested attribute (all Info types have this)
                current_explicitly_requested = getattr(target, "explicitly_requested", False)
                existing_explicitly_requested = getattr(unique_targets[source_path], "explicitly_requested", False)
                if current_explicitly_requested and not existing_explicitly_requested:
                    # Replace with the explicitly requested version
                    unique_targets[source_path] = target

        return list(unique_targets.values())

    def _expand_glob_pattern(
        self,
        path_str: str,
        all_targets: list[T],
        *,
        create_invalid_info: Callable[[str, str], T],
        create_pending_info: Callable[..., T],  # Takes (source_path, destination_path, *, is_directory)
    ) -> None:
        """Expand a glob pattern using ListDirectoryRequest and add matches to all_targets.

        Generic implementation that works with any FileOperationInfo type.

        Args:
            path_str: Glob pattern (e.g., "/path/to/*.txt")
            all_targets: List to append matching Info entries to
            create_invalid_info: Factory function to create invalid Info object
            create_pending_info: Factory function to create pending Info object (source_path, destination_path, is_directory)
        """
        # Parse the pattern into directory and pattern parts
        path = Path(path_str)

        # If the pattern has multiple parts with wildcards, we need to handle parent resolution
        # For now, we'll support patterns where only the last component has wildcards
        if self._is_glob_pattern(str(path.parent)):
            # Parent directory contains wildcards - this is more complex, treat as invalid
            all_targets.append(
                create_invalid_info(
                    path_str,
                    "Glob patterns in parent directories are not supported",
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
                    create_invalid_info(
                        path_str,
                        f"No files match pattern '{pattern}'",
                    )
                )
            else:
                # Add all matching entries as PENDING (explicitly requested via glob pattern)
                all_targets.extend(
                    create_pending_info(
                        entry.path,
                        "",  # Will be set during operation
                        is_directory=entry.is_dir,
                    )
                    for entry in matching_entries
                )
        else:
            # Directory doesn't exist or can't be accessed
            failure_msg = (
                result.failure_reason.value if isinstance(result, ListDirectoryResultFailure) else "Unknown error"
            )
            all_targets.append(
                create_invalid_info(
                    path_str,
                    failure_msg,
                )
            )

    def _collect_all_files(
        self,
        paths: list[str],
        info_class: type[Any],  # Dataclass type (e.g., CopyFileInfo, MoveFileInfo)
        pending_status: Enum,
        invalid_status: Enum,
    ) -> list[T]:
        """Generic method to collect all files/directories that will be operated on.

        Handles both explicit paths and glob patterns (e.g., "/path/to/*.txt").
        Glob patterns match individual files in a directory, not subdirectories.

        Args:
            paths: List of path strings to process
            info_class: The Info dataclass class (e.g., CopyFileInfo, MoveFileInfo)
            pending_status: The PENDING status enum value (e.g., CopyStatus.PENDING)
            invalid_status: The INVALID status enum value (e.g., CopyStatus.INVALID)

        Returns:
            List of Info objects with status set (PENDING for valid paths, INVALID for invalid paths)
        """
        all_targets: list[T] = []

        def create_pending_info(source_path: str, destination_path: str, *, is_directory: bool) -> T:
            # info_class is a dataclass with these fields (CopyFileInfo, MoveFileInfo, etc.)
            return info_class(  # type: ignore[call-arg]
                source_path=source_path,
                destination_path=destination_path,
                is_directory=is_directory,
                status=pending_status,
                explicitly_requested=True,
            )

        def create_invalid_info(source_path: str, failure_reason: str) -> T:
            # info_class is a dataclass with these fields (CopyFileInfo, MoveFileInfo, etc.)
            return info_class(  # type: ignore[call-arg]
                source_path=source_path,
                destination_path="",
                is_directory=False,
                status=invalid_status,
                failure_reason=failure_reason,
            )

        def expand_glob_pattern(path_str: str, targets: list[T]) -> None:
            self._expand_glob_pattern(
                path_str,
                targets,
                create_invalid_info=create_invalid_info,
                create_pending_info=create_pending_info,
            )

        return self._collect_all_targets(
            paths=paths,
            all_targets=all_targets,
            create_pending_info=create_pending_info,
            create_invalid_info=create_invalid_info,
            expand_glob_pattern=expand_glob_pattern,
        )
