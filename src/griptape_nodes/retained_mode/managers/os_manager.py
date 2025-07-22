import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    ChangeDirectoryRequest,
    ChangeDirectoryResultFailure,
    ChangeDirectoryResultSuccess,
    FileSystemEntry,
    GetCurrentDirectoryRequest,
    GetCurrentDirectoryResultFailure,
    GetCurrentDirectoryResultSuccess,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
    OpenAssociatedFileRequest,
    OpenAssociatedFileResultFailure,
    OpenAssociatedFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.event_manager import EventManager

console = Console()
logger = logging.getLogger("griptape_nodes")


@dataclass
class DiskSpaceInfo:
    """Information about disk space usage."""

    total: int
    used: int
    free: int


class OSManager:
    """A class to manage OS-level scenarios.

    Making its own class as some runtime environments and some customer requirements may dictate this as optional.
    This lays the groundwork to exclude specific functionality on a configuration basis.
    """

    def __init__(self, event_manager: EventManager | None = None):
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                request_type=OpenAssociatedFileRequest, callback=self.on_open_associated_file_request
            )
            event_manager.assign_manager_to_request_type(
                request_type=ListDirectoryRequest, callback=self.on_list_directory_request
            )
            event_manager.assign_manager_to_request_type(
                request_type=GetCurrentDirectoryRequest, callback=self.on_get_current_directory_request
            )
            event_manager.assign_manager_to_request_type(
                request_type=ChangeDirectoryRequest, callback=self.on_change_directory_request
            )
        self._current_dir = None

    @property
    def current_dir(self) -> Path:
        """Get the current directory."""
        if self._current_dir is None:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            self._current_dir = GriptapeNodes.ConfigManager().workspace_path
        return self._current_dir

    @current_dir.setter
    def current_dir(self, path: Path) -> None:
        """Set the current directory."""
        self._current_dir = path

    def _expand_path(self, path_str: str) -> Path:
        """Expand a path string, handling tilde and environment variables.

        Args:
            path_str: Path string that may contain ~ or environment variables

        Returns:
            Expanded Path object
        """
        # Expand tilde and environment variables
        expanded = os.path.expanduser(os.path.expandvars(path_str))
        return Path(expanded).resolve()

    def _validate_workspace_path(self, path: Path) -> tuple[bool, Path]:
        """Check if a path is within workspace and return relative path if it is.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_workspace_path, relative_or_absolute_path)
        """
        workspace = GriptapeNodes.ConfigManager().workspace_path

        # Ensure both paths are resolved for comparison
        path = path.resolve()
        workspace = workspace.resolve()

        logger.debug(f"Validating path: {path} against workspace: {workspace}")

        try:
            relative = path.relative_to(workspace)
            logger.debug(f"Path is within workspace, relative path: {relative}")
            return True, relative
        except ValueError:
            logger.debug(f"Path is outside workspace: {path}")
            return False, path

    @staticmethod
    def platform() -> str:
        return sys.platform

    @staticmethod
    def is_windows() -> bool:
        return sys.platform.startswith("win")

    @staticmethod
    def is_mac() -> bool:
        return sys.platform.startswith("darwin")

    @staticmethod
    def is_linux() -> bool:
        return sys.platform.startswith("linux")

    def replace_process(self, args: list[Any]) -> None:
        """Replace the current process with a new one.

        Args:
            args: The command and arguments to execute.
        """
        if self.is_windows():
            # excecvp is a nightmare on Windows, so we use subprocess.Popen instead
            # https://stackoverflow.com/questions/7004687/os-exec-on-windows
            subprocess.Popen(args)  # noqa: S603
            sys.exit(0)
        else:
            sys.stdout.flush()  # Recommended here https://docs.python.org/3/library/os.html#os.execvpe
            os.execvp(args[0], args)  # noqa: S606

    def on_open_associated_file_request(self, request: OpenAssociatedFileRequest) -> ResultPayload:  # noqa: PLR0911
        # Sanitize and validate the file path
        try:
            # Expand the path first
            path = self._expand_path(request.path_to_file)
        except (ValueError, RuntimeError):
            details = f"Invalid file path: '{request.path_to_file}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure()

        if not path.exists() or not path.is_file():
            details = f"File does not exist: '{path}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure()

        logger.info("Attempting to open: %s on platform: %s", path, sys.platform)

        try:
            platform_name = sys.platform
            if self.is_windows():
                # Linter complains but this is the recommended way on Windows
                # We can ignore this warning as we've validated the path
                os.startfile(str(path))  # noqa: S606 # pyright: ignore[reportAttributeAccessIssue]
                logger.info("Started file on Windows: %s", path)
            elif self.is_mac():
                # On macOS, open should be in a standard location
                subprocess.run(  # noqa: S603
                    ["/usr/bin/open", str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Started file on macOS: %s", path)
            elif self.is_linux():
                # Use full path to xdg-open to satisfy linter
                # Common locations for xdg-open:
                xdg_paths = ["/usr/bin/xdg-open", "/bin/xdg-open", "/usr/local/bin/xdg-open"]

                xdg_path = next((p for p in xdg_paths if Path(p).exists()), None)
                if not xdg_path:
                    logger.info("xdg-open not found in standard locations")
                    return OpenAssociatedFileResultFailure()

                subprocess.run(  # noqa: S603
                    [xdg_path, str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Started file on Linux: %s", path)
            else:
                details = f"Unsupported platform: '{platform_name}'"
                logger.info(details)
                return OpenAssociatedFileResultFailure()

            return OpenAssociatedFileResultSuccess()
        except subprocess.CalledProcessError as e:
            logger.error(
                "Process error when opening file: return code=%s, stdout=%s, stderr=%s",
                e.returncode,
                e.stdout,
                e.stderr,
            )
            return OpenAssociatedFileResultFailure()
        except Exception as e:
            logger.error("Exception occurred when trying to open file: %s", type(e).__name__)
            return OpenAssociatedFileResultFailure()

    def on_list_directory_request(self, request: ListDirectoryRequest) -> ResultPayload:
        """Handle a request to list directory contents."""
        try:
            # Get the directory path to list
            if request.directory_path is None:
                directory = self.current_dir
            # Handle relative paths in workspace mode
            elif request.workspace_only:
                # In workspace mode, resolve relative to current directory
                if os.path.isabs(request.directory_path):
                    directory = self._expand_path(request.directory_path)
                else:
                    directory = (self.current_dir / request.directory_path).resolve()
            else:
                # In system-wide mode, expand the path normally
                directory = self._expand_path(request.directory_path)

            # Check if directory exists
            if not directory.exists() or not directory.is_dir():
                logger.error(f"Directory does not exist or is not a directory: {directory}")
                return ListDirectoryResultFailure()

            # Check workspace constraints
            is_workspace_path, relative_or_abs_path = self._validate_workspace_path(directory)
            if request.workspace_only and not is_workspace_path:
                logger.error(f"Directory is outside workspace: {directory}")
                return ListDirectoryResultFailure()

            entries = []
            try:
                # List directory contents
                for entry in directory.iterdir():
                    # Skip hidden files if not requested
                    if not request.show_hidden and entry.name.startswith("."):
                        continue

                    try:
                        stat = entry.stat()
                        # Get path relative to workspace if within workspace
                        is_entry_in_workspace, entry_path = self._validate_workspace_path(entry)
                        entries.append(
                            FileSystemEntry(
                                name=entry.name,
                                path=str(entry_path),
                                is_dir=entry.is_dir(),
                                size=stat.st_size,
                                modified_time=stat.st_mtime,
                            )
                        )
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Could not stat entry {entry}: {e}")
                        continue

            except (OSError, PermissionError) as e:
                logger.error(f"Error listing directory {directory}: {e}")
                return ListDirectoryResultFailure()

            return ListDirectoryResultSuccess(
                entries=entries, current_path=str(relative_or_abs_path), is_workspace_path=is_workspace_path
            )

        except Exception as e:
            logger.error(f"Unexpected error in list_directory: {type(e).__name__}: {e}")
            return ListDirectoryResultFailure()

    def on_get_current_directory_request(self, request: GetCurrentDirectoryRequest) -> ResultPayload:
        """Handle a request to get the current working directory."""
        try:
            is_workspace_path, path = self._validate_workspace_path(self.current_dir)
            if request.workspace_only and not is_workspace_path:
                # If workspace only and we're outside, reset to workspace root
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                self.current_dir = GriptapeNodes.ConfigManager().workspace_path
                return GetCurrentDirectoryResultSuccess(path="", is_workspace_path=True)

            return GetCurrentDirectoryResultSuccess(path=str(path), is_workspace_path=is_workspace_path)
        except Exception as e:
            logger.error(f"Error getting current directory: {type(e).__name__}: {e}")
            return GetCurrentDirectoryResultFailure()

    def on_change_directory_request(self, request: ChangeDirectoryRequest) -> ResultPayload:
        """Handle a request to change the current working directory."""
        try:
            # Handle relative paths in workspace mode
            if request.workspace_only:
                # In workspace mode, resolve relative to current directory
                if os.path.isabs(request.directory_path):
                    new_dir = self._expand_path(request.directory_path)
                else:
                    new_dir = (self.current_dir / request.directory_path).resolve()
            else:
                # In system-wide mode, expand the path normally
                new_dir = self._expand_path(request.directory_path)

            # Check if the directory exists and is actually a directory
            if not new_dir.exists() or not new_dir.is_dir():
                logger.error(f"Directory does not exist or is not a directory: {new_dir}")
                return ChangeDirectoryResultFailure()

            # Check workspace constraints
            is_workspace_path, relative_or_abs_path = self._validate_workspace_path(new_dir)
            if request.workspace_only and not is_workspace_path:
                logger.error(f"Directory is outside workspace: {new_dir}")
                return ChangeDirectoryResultFailure()

            # Update the current directory
            self.current_dir = new_dir
            return ChangeDirectoryResultSuccess(new_path=str(relative_or_abs_path), is_workspace_path=is_workspace_path)

        except Exception as e:
            logger.error(f"Unexpected error in change_directory: {type(e).__name__}: {e}")
            return ChangeDirectoryResultFailure()

    @staticmethod
    def get_disk_space_info(path: Path) -> DiskSpaceInfo:
        """Get disk space information for a given path.

        Args:
            path: The path to check disk space for.

        Returns:
            DiskSpaceInfo with total, used, and free disk space in bytes.
        """
        stat = shutil.disk_usage(path)
        return DiskSpaceInfo(total=stat.total, used=stat.used, free=stat.free)

    @staticmethod
    def check_available_disk_space(path: Path, required_gb: float) -> bool:
        """Check if there is enough available disk space at the given path.

        Args:
            path: The path to check disk space for
            required_gb: Required space in gigabytes

        Returns:
            bool: True if enough space is available, False otherwise
        """
        try:
            disk_space = OSManager.get_disk_space_info(path)
            required_bytes = int(required_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
            return disk_space.free >= required_bytes
        except Exception as e:
            logger.error("Failed to check disk space: %s", e)
            return False

    @staticmethod
    def format_disk_space_error(path: Path) -> str:
        """Format a disk space error message with available space information.

        Args:
            path: The path to check disk space for

        Returns:
            str: Formatted error message with available space
        """
        try:
            disk_space = OSManager.get_disk_space_info(path)
            free_gb = disk_space.free / (1024 * 1024 * 1024)  # Convert GB to bytes
            return f"Insufficient disk space. Only {free_gb:.1f} GB available at {path}"
        except Exception as e:
            return f"Could not determine available disk space at {path}: {e}"

    @staticmethod
    def cleanup_directory_if_needed(full_directory_path: Path, max_size_gb: float) -> bool:
        """Check directory size and cleanup old files if needed.

        Args:
            full_directory_path: Path to the directory to check and clean
            max_size_gb: Target size in GB

        Returns:
            True if cleanup was performed, False otherwise
        """
        if max_size_gb < 0:
            logger.warning(
                "Asked to clean up directory to be below a negative threshold. Overriding to a size of 0 GB."
            )
            max_size_gb = 0

        # Calculate current directory size
        current_size_gb = OSManager._get_directory_size_gb(full_directory_path)

        if current_size_gb <= max_size_gb:
            return False

        logger.info(
            "Directory %s size (%.1f GB) exceeds limit (%s GB). Starting cleanup...",
            full_directory_path,
            current_size_gb,
            max_size_gb,
        )

        # Perform cleanup
        return OSManager._cleanup_old_files(full_directory_path, max_size_gb)

    @staticmethod
    def _get_directory_size_gb(path: Path) -> float:
        """Get total size of directory in GB.

        Args:
            path: Path to the directory

        Returns:
            Total size in GB
        """
        total_size = 0.0

        if not path.exists():
            logger.error("Directory %s does not exist. Skipping cleanup.", path)
            return 0.0

        for _, _, files in os.walk(path):
            for f in files:
                fp = path / f
                if not fp.is_symlink():
                    total_size += fp.stat().st_size
        return total_size / (1024 * 1024 * 1024)  # Convert to GB

    @staticmethod
    def _cleanup_old_files(directory_path: Path, target_size_gb: float) -> bool:
        """Remove oldest files until directory is under target size.

        Args:
            directory_path: Path to the directory to clean
            target_size_gb: Target size in GB

        Returns:
            True if files were removed, False otherwise
        """
        if not directory_path.exists():
            logger.error("Directory %s does not exist. Skipping cleanup.", directory_path)
            return False

        # Get all files with their modification times
        files_with_times: list[tuple[Path, float]] = []

        for file_path in directory_path.rglob("*"):
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    files_with_times.append((file_path, mtime))
                except (OSError, FileNotFoundError) as err:
                    # Skip files that can't be accessed
                    logger.error(
                        "While cleaning up old files, saw file %s. File could not be accessed; skipping. Error: %s",
                        file_path,
                        err,
                    )
                    continue

        if not files_with_times:
            logger.error(
                "Attempted to clean up files to get below a target directory size, but no suitable files were found that could be deleted."
            )
            return False

        # Sort by modification time (oldest first)
        files_with_times.sort(key=lambda x: x[1])

        # Remove files until we're under the target size
        removed_count = 0

        for file_path, _ in files_with_times:
            try:
                # Delete the file.
                file_path.unlink()
                removed_count += 1

                # Check if we're now under the target size
                current_size_gb = OSManager._get_directory_size_gb(directory_path)
                if current_size_gb <= target_size_gb:
                    # We're done!
                    break

            except (OSError, FileNotFoundError) as err:
                # Skip files that can't be deleted
                logger.error(
                    "While cleaning up old files, attempted to delete file %s. File could not be deleted; skipping. Deletion error: %s",
                    file_path,
                    err,
                )

        if removed_count > 0:
            final_size_gb = OSManager._get_directory_size_gb(directory_path)
            logger.info(
                "Cleaned up %d old files from %s. Directory size reduced to %.1f GB",
                removed_count,
                directory_path,
                final_size_gb,
            )
        else:
            # None deleted.
            logger.error("Attempted to clean up old files from %s, but no files could be deleted.")

        return removed_count > 0
