import base64
import mimetypes
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from binaryornot.check import is_binary
from rich.console import Console

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    CreateFileRequest,
    CreateFileResultFailure,
    CreateFileResultSuccess,
    FileSystemEntry,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
    OpenAssociatedFileRequest,
    OpenAssociatedFileResultFailure,
    OpenAssociatedFileResultSuccess,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    RenameFileRequest,
    RenameFileResultFailure,
    RenameFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.retained_mode.managers.event_manager import EventManager

console = Console()


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
                request_type=ReadFileRequest, callback=self.on_read_file_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=CreateFileRequest, callback=self.on_create_file_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=RenameFileRequest, callback=self.on_rename_file_request
            )

    def _get_workspace_path(self) -> Path:
        """Get the workspace path from config."""
        return GriptapeNodes.ConfigManager().workspace_path

    def _expand_path(self, path_str: str) -> Path:
        """Expand a path string, handling tilde and environment variables.

        Args:
            path_str: Path string that may contain ~ or environment variables

        Returns:
            Expanded Path object
        """
        # Expand environment variables first, then tilde
        expanded_vars = os.path.expandvars(path_str)
        return Path(expanded_vars).expanduser().resolve()

    def _resolve_file_path(self, path_str: str, *, workspace_only: bool = False) -> Path:
        """Resolve a file path, handling absolute, relative, and tilde paths.

        Args:
            path_str: Path string that may be absolute, relative, or start with ~
            workspace_only: If True and path is invalid, fall back to workspace directory

        Returns:
            Resolved Path object
        """
        try:
            if Path(path_str).is_absolute() or path_str.startswith("~"):
                # Expand tilde and environment variables for absolute paths or paths starting with ~
                return self._expand_path(path_str)
            # Both workspace and system-wide modes resolve relative to current directory
            return (self._get_workspace_path() / path_str).resolve()
        except (ValueError, RuntimeError):
            if workspace_only:
                msg = f"Path '{path_str}' not found, using workspace directory: {self._get_workspace_path()}"
                logger.warning(msg)
                return self._get_workspace_path()
            # Re-raise the exception for non-workspace mode
            raise

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

        msg = f"Validating path: {path} against workspace: {workspace}"
        logger.debug(msg)

        try:
            relative = path.relative_to(workspace)
        except ValueError:
            msg = f"Path is outside workspace: {path}"
            logger.debug(msg)
            return False, path

        msg = f"Path is within workspace, relative path: {relative}"
        logger.debug(msg)
        return True, relative

    def _validate_read_file_request(self, request: ReadFileRequest) -> tuple[Path, str]:
        """Validate read file request and return resolved file path and path string."""
        # Validate that exactly one of file_path or file_entry is provided
        if request.file_path is None and request.file_entry is None:
            msg = "Either file_path or file_entry must be provided"
            logger.error(msg)
            raise ValueError(msg)

        if request.file_path is not None and request.file_entry is not None:
            msg = "Only one of file_path or file_entry should be provided, not both"
            logger.error(msg)
            raise ValueError(msg)

        # Get the file path to read - handle paths consistently
        if request.file_entry is not None:
            file_path_str = request.file_entry.path
        elif request.file_path is not None:
            file_path_str = request.file_path
        else:
            msg = "No valid file path provided"
            logger.error(msg)
            raise ValueError(msg)

        file_path = self._resolve_file_path(file_path_str, workspace_only=request.workspace_only is True)

        # Check if file exists and is actually a file
        if not file_path.exists():
            msg = f"File does not exist: {file_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)
        if not file_path.is_file():
            msg = f"File is not a file: {file_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        # Check workspace constraints
        is_workspace_path, _ = self._validate_workspace_path(file_path)
        if request.workspace_only and not is_workspace_path:
            msg = f"File is outside workspace: {file_path}"
            logger.error(msg)
            raise ValueError(msg)

        return file_path, file_path_str

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

    def on_open_associated_file_request(self, request: OpenAssociatedFileRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901
        # Validate that exactly one of path_to_file or file_entry is provided
        if request.path_to_file is None and request.file_entry is None:
            msg = "Either path_to_file or file_entry must be provided"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(result_details=msg)

        if request.path_to_file is not None and request.file_entry is not None:
            msg = "Only one of path_to_file or file_entry should be provided, not both"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(result_details=msg)

        # Get the file path to open
        if request.file_entry is not None:
            # Use the path from the FileSystemEntry
            file_path_str = request.file_entry.path
        elif request.path_to_file is not None:
            # Use the provided path_to_file
            file_path_str = request.path_to_file
        else:
            # This should never happen due to validation above, but type checker needs it
            msg = "No valid file path provided"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(result_details=msg)

        # At this point, file_path_str is guaranteed to be a string
        if file_path_str is None:
            msg = "No valid file path provided"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(result_details=msg)

        # Sanitize and validate the path (file or directory)
        try:
            # Resolve the path (no workspace fallback for open requests)
            path = self._resolve_file_path(file_path_str, workspace_only=False)
        except (ValueError, RuntimeError):
            details = f"Invalid file path: '{file_path_str}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure(result_details=details)

        if not path.exists():
            details = f"Path does not exist: '{path}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure(result_details=details)

        logger.info("Attempting to open path: %s on platform: %s", path, sys.platform)

        try:
            platform_name = sys.platform
            if self.is_windows():
                # Linter complains but this is the recommended way on Windows
                # We can ignore this warning as we've validated the path
                os.startfile(str(path))  # noqa: S606 # pyright: ignore[reportAttributeAccessIssue]
                logger.info("Opened path on Windows: %s", path)
            elif self.is_mac():
                # On macOS, open should be in a standard location
                subprocess.run(  # noqa: S603
                    ["/usr/bin/open", str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Opened path on macOS: %s", path)
            elif self.is_linux():
                # Use full path to xdg-open to satisfy linter
                # Common locations for xdg-open:
                xdg_paths = ["/usr/bin/xdg-open", "/bin/xdg-open", "/usr/local/bin/xdg-open"]

                xdg_path = next((p for p in xdg_paths if Path(p).exists()), None)
                if not xdg_path:
                    details = "xdg-open not found in standard locations"
                    logger.info(details)
                    return OpenAssociatedFileResultFailure(result_details=details)

                subprocess.run(  # noqa: S603
                    [xdg_path, str(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Opened path on Linux: %s", path)
            else:
                details = f"Unsupported platform: '{platform_name}'"
                logger.info(details)
                return OpenAssociatedFileResultFailure(result_details=details)

            return OpenAssociatedFileResultSuccess()
        except subprocess.CalledProcessError as e:
            details = (
                f"Process error when opening file: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"
            )
            logger.error(details)
            return OpenAssociatedFileResultFailure(result_details=details)
        except Exception as e:
            details = f"Exception occurred when trying to open path: {e}"
            logger.error(details)
            return OpenAssociatedFileResultFailure(result_details=details)

    def _detect_mime_type(self, file_path: Path) -> str | None:
        """Detect MIME type for a file. Returns None for directories or if detection fails."""
        if file_path.is_dir():
            return None

        try:
            mime_type, _ = mimetypes.guess_type(str(file_path), strict=True)
            if mime_type is None:
                mime_type = "text/plain"
            return mime_type  # noqa: TRY300
        except Exception as e:
            msg = f"MIME type detection failed for {file_path}: {e}"
            logger.warning(msg)
            return "text/plain"

    def on_list_directory_request(self, request: ListDirectoryRequest) -> ResultPayload:  # noqa: C901, PLR0911
        """Handle a request to list directory contents."""
        try:
            # Get the directory path to list
            if request.directory_path is None:
                directory = self._get_workspace_path()
            # Handle paths consistently - always resolve relative paths relative to current directory
            elif Path(request.directory_path).is_absolute() or request.directory_path.startswith("~"):
                # Expand tilde and environment variables for absolute paths or paths starting with ~
                directory = self._expand_path(request.directory_path)
            else:
                # Both workspace and system-wide modes resolve relative to current directory
                directory = (self._get_workspace_path() / request.directory_path).resolve()

            # Check if directory exists
            if not directory.exists():
                msg = f"Directory does not exist: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(result_details=msg)
            if not directory.is_dir():
                msg = f"Directory is not a directory: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(result_details=msg)

            # Check workspace constraints
            is_workspace_path, relative_or_abs_path = self._validate_workspace_path(directory)
            if request.workspace_only and not is_workspace_path:
                msg = f"Directory is outside workspace: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(result_details=msg)

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
                        mime_type = self._detect_mime_type(entry)
                        entries.append(
                            FileSystemEntry(
                                name=entry.name,
                                path=str(entry_path),
                                is_dir=entry.is_dir(),
                                size=stat.st_size,
                                modified_time=stat.st_mtime,
                                mime_type=mime_type,
                            )
                        )
                    except (OSError, PermissionError) as e:
                        msg = f"Could not stat entry {entry}: {e}"
                        logger.warning(msg)
                        continue

            except (OSError, PermissionError) as e:
                msg = f"Error listing directory {directory}: {e}"
                logger.error(msg)
                return ListDirectoryResultFailure(result_details=msg)

            # Return appropriate path format based on mode
            if request.workspace_only:
                # In workspace mode, return relative path if within workspace, absolute if outside
                return ListDirectoryResultSuccess(
                    entries=entries, current_path=str(relative_or_abs_path), is_workspace_path=is_workspace_path
                )
            # In system-wide mode, always return the full absolute path
            return ListDirectoryResultSuccess(
                entries=entries, current_path=str(directory), is_workspace_path=is_workspace_path
            )

        except Exception as e:
            msg = f"Unexpected error in list_directory: {type(e).__name__}: {e}"
            logger.error(msg)
            return ListDirectoryResultFailure(result_details=msg)

    def on_read_file_request(self, request: ReadFileRequest) -> ResultPayload:
        """Handle a request to read file contents with automatic text/binary detection."""
        # Initialize variables that might be used in exception handlers
        file_path: Path | None = None
        file_path_str: str | None = None

        try:
            # Validate request and get file path
            file_path, file_path_str = self._validate_read_file_request(request)

            # Read file content
            content, encoding, mime_type, compression_encoding, file_size = self._read_file_content(file_path, request)

            return ReadFileResultSuccess(
                content=content,
                file_size=file_size,
                mime_type=mime_type,
                encoding=encoding,
                compression_encoding=compression_encoding,
            )

        except (ValueError, FileNotFoundError) as e:
            file_info = f" for file: {file_path}" if file_path is not None else ""
            msg = f"Validation error in read_file{file_info}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(result_details=msg)
        except Exception as e:
            # Try to include file path in error message if available
            path_info = ""
            if file_path is not None:
                path_info = f" for {file_path}"
            elif file_path_str is not None:
                path_info = f" for {file_path_str}"

            msg = f"Unexpected error in read_file{path_info}: {type(e).__name__}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(result_details=msg)

    def _read_file_content(
        self, file_path: Path, request: ReadFileRequest
    ) -> tuple[bytes | str, str | None, str, str | None, int]:
        """Read file content and return content, encoding, mime_type, compression_encoding, and file_size."""
        # Get file size
        file_size = file_path.stat().st_size

        # Determine MIME type and compression encoding
        mime_type, compression_encoding = mimetypes.guess_type(str(file_path), strict=True)
        if mime_type is None:
            mime_type = "text/plain"

        # Determine if file is binary
        try:
            is_binary_file = is_binary(str(file_path))
        except Exception as e:
            msg = f"binaryornot detection failed for {file_path}: {e}"
            logger.warning(msg)
            is_binary_file = not mime_type.startswith(
                ("text/", "application/json", "application/xml", "application/yaml")
            )

        # Read file content
        if not is_binary_file:
            content, encoding = self._read_text_file(file_path, request.encoding)
        else:
            content, encoding = self._read_binary_file(file_path, mime_type)

        return content, encoding, mime_type, compression_encoding, file_size

    def _read_text_file(self, file_path: Path, requested_encoding: str) -> tuple[bytes | str, str | None]:
        """Read file as text with fallback encodings."""
        try:
            with file_path.open(encoding=requested_encoding) as f:
                return f.read(), requested_encoding
        except UnicodeDecodeError:
            try:
                with file_path.open(encoding="utf-8") as f:
                    return f.read(), "utf-8"
            except UnicodeDecodeError:
                with file_path.open("rb") as f:
                    return f.read(), None

    def _read_binary_file(self, file_path: Path, mime_type: str) -> tuple[bytes | str, None]:
        """Read file as binary, with special handling for images."""
        with file_path.open("rb") as f:
            content = f.read()

        if mime_type.startswith("image/"):
            content = self._handle_image_content(content, file_path, mime_type)

        return content, None

    def _handle_image_content(self, content: bytes, file_path: Path, mime_type: str) -> str:
        """Handle image content by creating previews or returning static URLs."""
        # Store original bytes for preview creation
        original_image_bytes = content

        # Check if file is already in the static files directory
        config_manager = GriptapeNodes.ConfigManager()
        static_files_directory = config_manager.get_config_value("static_files_directory", default="staticfiles")
        static_dir = config_manager.workspace_path / static_files_directory

        try:
            # Check if file is within the static files directory
            file_relative_to_static = file_path.relative_to(static_dir)
            # File is in static directory, construct URL directly
            static_url = f"http://localhost:8124/static/{file_relative_to_static}"
            msg = f"Image already in static directory, returning URL: {static_url}"
            logger.debug(msg)
        except ValueError:
            # File is not in static directory, create small preview
            from griptape_nodes.utils.image_preview import create_image_preview_from_bytes

            preview_data_url = create_image_preview_from_bytes(
                original_image_bytes,  # type: ignore[arg-type]
                max_width=200,
                max_height=200,
                quality=85,
                image_format="WEBP",
            )

            if preview_data_url:
                logger.debug("Image preview created (file not moved)")
                return preview_data_url
            # Fallback to data URL if preview creation fails
            data_url = f"data:{mime_type};base64,{base64.b64encode(original_image_bytes).decode('utf-8')}"
            logger.debug("Fallback to full image data URL")
            return data_url
        else:
            return static_url

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
        """Check if there is sufficient disk space available.

        Args:
            path: The path to check disk space for.
            required_gb: The minimum disk space required in GB.

        Returns:
            True if sufficient space is available, False otherwise.
        """
        try:
            disk_info = OSManager.get_disk_space_info(path)
            required_bytes = int(required_gb * 1024 * 1024 * 1024)  # Convert GB to bytes
            return disk_info.free >= required_bytes  # noqa: TRY300
        except OSError:
            return False

    @staticmethod
    def format_disk_space_error(path: Path, exception: Exception | None = None) -> str:
        """Format a user-friendly disk space error message.

        Args:
            path: The path where the disk space issue occurred.
            exception: The original exception, if any.

        Returns:
            A formatted error message with disk space information.
        """
        try:
            disk_info = OSManager.get_disk_space_info(path)
            free_gb = disk_info.free / (1024**3)
            used_gb = disk_info.used / (1024**3)
            total_gb = disk_info.total / (1024**3)

            error_msg = f"Insufficient disk space at {path}. "
            error_msg += f"Available: {free_gb:.2f} GB, Used: {used_gb:.2f} GB, Total: {total_gb:.2f} GB. "

            if exception:
                error_msg += f"Error: {exception}"
            else:
                error_msg += "Please free up disk space and try again."

            return error_msg  # noqa: TRY300
        except OSError:
            return f"Could not determine disk space at {path}. Please check disk space manually."

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

    def on_create_file_request(self, request: CreateFileRequest) -> ResultPayload:
        """Handle a request to create a file or directory."""
        try:
            # Get the full path using the new method
            full_path_str = request.get_full_path()

            # Determine if path is absolute (not constrained to workspace)
            is_absolute = Path(full_path_str).is_absolute()

            # If workspace_only is True and path is absolute, it's outside workspace
            if request.workspace_only and is_absolute:
                msg = f"Absolute path is outside workspace: {full_path_str}"
                logger.error(msg)
                return CreateFileResultFailure(result_details=msg)

            # Resolve path - if absolute, use as-is; if relative, align to workspace
            if is_absolute:
                file_path = Path(full_path_str).resolve()
            else:
                file_path = (self._get_workspace_path() / full_path_str).resolve()

            # Check if it already exists - warn but treat as success
            if file_path.exists():
                msg = f"Path already exists: {file_path}"
                logger.warning(msg)
                return CreateFileResultSuccess(created_path=str(file_path))

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if request.is_directory:
                file_path.mkdir()
                logger.info("Created directory: %s", file_path)
            # Create file with optional content
            elif request.content is not None:
                with file_path.open("w", encoding=request.encoding) as f:
                    f.write(request.content)
                logger.info("Created file with content: %s", file_path)
            else:
                file_path.touch()
                logger.info("Created empty file: %s", file_path)

            return CreateFileResultSuccess(created_path=str(file_path))

        except Exception as e:
            path_info = request.get_full_path() if hasattr(request, "get_full_path") else str(request.path)
            msg = f"Failed to create {'directory' if request.is_directory else 'file'} at {path_info}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(result_details=msg)

    def on_rename_file_request(self, request: RenameFileRequest) -> ResultPayload:
        """Handle a request to rename a file or directory."""
        try:
            # Resolve and validate old path
            old_path = self._resolve_file_path(request.old_path, workspace_only=request.workspace_only is True)

            # Resolve and validate new path
            new_path = self._resolve_file_path(request.new_path, workspace_only=request.workspace_only is True)

            # Check if old path exists
            if not old_path.exists():
                msg = f"Source path does not exist: {old_path}"
                logger.error(msg)
                return RenameFileResultFailure(result_details=msg)

            # Check if new path already exists
            if new_path.exists():
                msg = f"Destination path already exists: {new_path}"
                logger.error(msg)
                return RenameFileResultFailure(result_details=msg)

            # Check workspace constraints for both paths
            is_old_in_workspace, _ = self._validate_workspace_path(old_path)
            is_new_in_workspace, _ = self._validate_workspace_path(new_path)

            if request.workspace_only and (not is_old_in_workspace or not is_new_in_workspace):
                msg = f"One or both paths are outside workspace: {old_path} -> {new_path}"
                logger.error(msg)
                return RenameFileResultFailure(result_details=msg)

            # Create parent directories for new path if needed
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Perform the rename operation
            old_path.rename(new_path)
            logger.info("Renamed: %s -> %s", old_path, new_path)

            return RenameFileResultSuccess(old_path=str(old_path), new_path=str(new_path))

        except Exception as e:
            msg = f"Failed to rename {request.old_path} to {request.new_path}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(result_details=msg)
