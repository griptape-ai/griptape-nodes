import base64
import logging
import mimetypes
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import aioshutil
from binaryornot.check import is_binary
from rich.console import Console

from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.base_events import ResultDetails, ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    CopyFileRequest,
    CopyFileResultFailure,
    CopyFileResultSuccess,
    CopyTreeRequest,
    CopyTreeResultFailure,
    CopyTreeResultSuccess,
    CreateFileRequest,
    CreateFileResultFailure,
    CreateFileResultSuccess,
    DeleteFileRequest,
    DeleteFileResultFailure,
    DeleteFileResultSuccess,
    ExistingFilePolicy,
    FileIOFailureReason,
    FileSystemEntry,
    GetFileInfoRequest,
    GetFileInfoResultFailure,
    GetFileInfoResultSuccess,
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
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.resource_events import (
    CreateResourceInstanceRequest,
    CreateResourceInstanceResultSuccess,
    RegisterResourceTypeRequest,
    RegisterResourceTypeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.resource_types.cpu_resource import CPUResourceType
from griptape_nodes.retained_mode.managers.resource_types.os_resource import OSResourceType

console = Console()

# Windows MAX_PATH limit - paths longer than this need \\?\ prefix
WINDOWS_MAX_PATH = 260


@dataclass
class DiskSpaceInfo:
    """Information about disk space usage."""

    total: int
    used: int
    free: int


class FileContentResult(NamedTuple):
    """Result from reading file content."""

    content: str | bytes
    encoding: str | None
    mime_type: str
    compression_encoding: str | None
    file_size: int


@dataclass
class CopyTreeValidationResult:
    """Result from validating copy tree paths."""

    source_normalized: str
    dest_normalized: str
    source_path: Path
    destination_path: Path


@dataclass
class CopyTreeStats:
    """Statistics from copying a directory tree."""

    files_copied: int
    total_bytes_copied: int


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

            event_manager.assign_manager_to_request_type(
                request_type=WriteFileRequest, callback=self.on_write_file_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=CopyTreeRequest, callback=self.on_copy_tree_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=CopyFileRequest, callback=self.on_copy_file_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=DeleteFileRequest, callback=self.on_delete_file_request
            )

            event_manager.assign_manager_to_request_type(
                request_type=GetFileInfoRequest, callback=self.on_get_file_info_request
            )

            # Register for app initialization event to setup system resources
            event_manager.add_listener_to_app_event(AppInitializationComplete, self.on_app_initialization_complete)

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
        return self.resolve_path_safely(Path(expanded_vars).expanduser())

    def resolve_path_safely(self, path: Path) -> Path:
        """Resolve a path consistently across platforms.

        Unlike Path.resolve() which behaves differently on Windows vs Unix
        for non-existent paths, this method provides consistent behavior:
        - Converts relative paths to absolute (using CWD as base)
        - Normalizes path separators and removes . and ..
        - Does NOT resolve symlinks if path doesn't exist
        - Does NOT change path based on CWD for absolute paths

        Use this instead of .resolve() when:
        - Path might not exist (file creation, validation, user input)
        - You need consistent cross-platform comparison
        - You're about to create the file/directory

        Use .resolve() when:
        - Path definitely exists and you need symlink resolution
        - You're checking actual file locations

        Args:
            path: Path to resolve (relative or absolute, existing or not)

        Returns:
            Absolute, normalized Path object

        Examples:
            # Relative path
            resolve_path_safely(Path("relative/file.txt"))
            → Path("/current/dir/relative/file.txt")

            # Absolute non-existent path (Windows safe)
            resolve_path_safely(Path("/abs/nonexistent/path"))
            → Path("/abs/nonexistent/path")  # NOT resolved relative to CWD
        """
        # Convert to absolute if relative
        if not path.is_absolute():
            path = Path.cwd() / path

        # Normalize (remove . and .., collapse slashes) without resolving symlinks
        # This works consistently even for non-existent paths on Windows
        return Path(os.path.normpath(path))

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
            return self.resolve_path_safely(self._get_workspace_path() / path_str)
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
        # Both path and workspace should use .resolve() to follow symlinks consistently
        # (e.g., /var -> /private/var on macOS). Even if path doesn't exist yet,
        # .resolve() will resolve parent directories and symlinks in the path.
        path = path.resolve()
        workspace = workspace.resolve()  # Workspace should always exist

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

    def normalize_path_for_platform(self, path: Path) -> str:
        r"""Convert Path to string with Windows long path support if needed.

        Windows has a 260 character path limit (MAX_PATH). Paths longer than this
        need the \\?\ prefix to work correctly. This method transparently adds
        the prefix when needed on Windows.

        Note: This method assumes the path exists or will exist. For non-existent
        paths that need cross-platform normalization, use resolve_path_safely() first.

        Args:
            path: Path object to convert to string

        Returns:
            String representation of path, with Windows long path prefix if needed
        """
        path_str = str(path.resolve())

        # Windows long path handling (paths > WINDOWS_MAX_PATH chars need \\?\ prefix)
        if self.is_windows() and len(path_str) >= WINDOWS_MAX_PATH and not path_str.startswith("\\\\?\\"):
            # UNC paths (\\server\share) need \\?\UNC\ prefix
            if path_str.startswith("\\\\"):
                return f"\\\\?\\UNC\\{path_str[2:]}"
            # Regular paths need \\?\ prefix
            return f"\\\\?\\{path_str}"

        return path_str

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
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        if request.path_to_file is not None and request.file_entry is not None:
            msg = "Only one of path_to_file or file_entry should be provided, not both"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

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
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # At this point, file_path_str is guaranteed to be a string
        if file_path_str is None:
            msg = "No valid file path provided"
            logger.error(msg)
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Sanitize and validate the path (file or directory)
        try:
            # Resolve the path (no workspace fallback for open requests)
            path = self._resolve_file_path(file_path_str, workspace_only=False)
        except (ValueError, RuntimeError):
            details = f"Invalid file path: '{file_path_str}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure(
                failure_reason=FileIOFailureReason.INVALID_PATH, result_details=details
            )

        if not path.exists():
            details = f"Path does not exist: '{path}'"
            logger.info(details)
            return OpenAssociatedFileResultFailure(
                failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=details
            )

        logger.info("Attempting to open path: %s on platform: %s", path, sys.platform)

        try:
            platform_name = sys.platform
            if self.is_windows():
                # Linter complains but this is the recommended way on Windows
                # We can ignore this warning as we've validated the path
                os.startfile(self.normalize_path_for_platform(path))  # noqa: S606 # pyright: ignore[reportAttributeAccessIssue]
                logger.info("Opened path on Windows: %s", path)
            elif self.is_mac():
                # On macOS, open should be in a standard location
                subprocess.run(  # noqa: S603
                    ["/usr/bin/open", self.normalize_path_for_platform(path)],
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
                    return OpenAssociatedFileResultFailure(
                        failure_reason=FileIOFailureReason.IO_ERROR, result_details=details
                    )

                subprocess.run(  # noqa: S603
                    [xdg_path, self.normalize_path_for_platform(path)],
                    check=True,  # Explicitly use check
                    capture_output=True,
                    text=True,
                )
                logger.info("Opened path on Linux: %s", path)
            else:
                details = f"Unsupported platform: '{platform_name}'"
                logger.info(details)
                return OpenAssociatedFileResultFailure(
                    failure_reason=FileIOFailureReason.IO_ERROR, result_details=details
                )

            return OpenAssociatedFileResultSuccess(result_details="File opened successfully in associated application.")
        except subprocess.CalledProcessError as e:
            details = (
                f"Process error when opening file: return code={e.returncode}, stdout={e.stdout}, stderr={e.stderr}"
            )
            logger.error(details)
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=details)
        except Exception as e:
            details = f"Exception occurred when trying to open path: {e}"
            logger.error(details)
            return OpenAssociatedFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=details)

    def _detect_mime_type(self, file_path: Path) -> str | None:
        """Detect MIME type for a file. Returns None for directories or if detection fails."""
        if file_path.is_dir():
            return None

        try:
            mime_type, _ = mimetypes.guess_type(self.normalize_path_for_platform(file_path), strict=True)
            if mime_type is None:
                mime_type = "text/plain"
            return mime_type  # noqa: TRY300
        except Exception as e:
            msg = f"MIME type detection failed for {file_path}: {e}"
            logger.warning(msg)
            return "text/plain"

    def on_list_directory_request(self, request: ListDirectoryRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912
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
                directory = self.resolve_path_safely(self._get_workspace_path() / request.directory_path)

            # Check if directory exists
            if not directory.exists():
                msg = f"Directory does not exist: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)
            if not directory.is_dir():
                msg = f"Path is not a directory: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

            # Check workspace constraints
            is_workspace_path, relative_or_abs_path = self._validate_workspace_path(directory)
            if request.workspace_only and not is_workspace_path:
                msg = f"Directory is outside workspace: {directory}"
                logger.error(msg)
                return ListDirectoryResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

            entries = []
            try:
                # List directory contents
                for entry in directory.iterdir():
                    # Skip hidden files if not requested
                    if not request.show_hidden and entry.name.startswith("."):
                        continue

                    # Apply pattern filter if specified
                    if request.pattern is not None and not entry.match(request.pattern):
                        continue

                    try:
                        stat = entry.stat()
                        # Get path relative to workspace if within workspace
                        _, entry_path = self._validate_workspace_path(entry)
                        # Also get absolute resolved path
                        absolute_resolved_path = str(entry.resolve())
                        mime_type = self._detect_mime_type(entry)
                        entries.append(
                            FileSystemEntry(
                                name=entry.name,
                                path=str(entry_path),
                                is_dir=entry.is_dir(),
                                size=stat.st_size,
                                modified_time=stat.st_mtime,
                                mime_type=mime_type,
                                absolute_path=absolute_resolved_path,
                            )
                        )
                    except (OSError, PermissionError) as e:
                        msg = f"Could not stat entry {entry}: {e}"
                        logger.warning(msg)
                        continue

            except PermissionError as e:
                msg = f"Permission denied listing directory {directory}: {e}"
                logger.error(msg)
                return ListDirectoryResultFailure(
                    failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg
                )
            except OSError as e:
                msg = f"I/O error listing directory {directory}: {e}"
                logger.error(msg)
                return ListDirectoryResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

            # Return appropriate path format based on mode
            if request.workspace_only:
                # In workspace mode, return relative path if within workspace, absolute if outside
                return ListDirectoryResultSuccess(
                    entries=entries,
                    current_path=str(relative_or_abs_path),
                    is_workspace_path=is_workspace_path,
                    result_details="Directory listing retrieved successfully.",
                )
            # In system-wide mode, always return the full absolute path
            return ListDirectoryResultSuccess(
                entries=entries,
                current_path=str(directory),
                is_workspace_path=is_workspace_path,
                result_details="Directory listing retrieved successfully.",
            )

        except Exception as e:
            msg = f"Unexpected error in list_directory: {type(e).__name__}: {e}"
            logger.error(msg)
            return ListDirectoryResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

    def on_read_file_request(self, request: ReadFileRequest) -> ResultPayload:  # noqa: PLR0911
        """Handle a request to read file contents with automatic text/binary detection."""
        # Validate request and get file path
        try:
            file_path, _file_path_str = self._validate_read_file_request(request)
        except FileNotFoundError as e:
            msg = f"File not found: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)
        except PermissionError as e:
            msg = f"Permission denied: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid path: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)
        except OSError as e:
            msg = f"I/O error validating path: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Read file content
        try:
            result = self._read_file_content(file_path, request)
        except PermissionError as e:
            msg = f"Permission denied for file {file_path}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except IsADirectoryError:
            msg = f"Path is a directory, not a file: {file_path}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.IS_DIRECTORY, result_details=msg)
        except UnicodeDecodeError as e:
            msg = f"Encoding error for file {file_path}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.ENCODING_ERROR, result_details=msg)
        except OSError as e:
            msg = f"I/O error for file {file_path}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error reading file {file_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return ReadFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH - Only reached if no exceptions occurred
        return ReadFileResultSuccess(
            content=result.content,
            file_size=result.file_size,
            mime_type=result.mime_type,
            encoding=result.encoding,
            compression_encoding=result.compression_encoding,
            result_details="File read successfully.",
        )

    def _read_file_content(self, file_path: Path, request: ReadFileRequest) -> FileContentResult:
        """Read file content and return FileContentResult with all file information."""
        # Get file size
        file_size = file_path.stat().st_size

        # Determine MIME type and compression encoding
        normalized_path = self.normalize_path_for_platform(file_path)
        mime_type, compression_encoding = mimetypes.guess_type(normalized_path, strict=True)
        if mime_type is None:
            mime_type = "text/plain"

        # Determine if file is binary
        try:
            is_binary_file = is_binary(normalized_path)
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

        return FileContentResult(
            content=content,
            encoding=encoding,
            mime_type=mime_type,
            compression_encoding=compression_encoding,
            file_size=file_size,
        )

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
        static_dir = config_manager.workspace_path

        try:
            # Check if file is within the static files directory
            file_relative_to_static = file_path.relative_to(static_dir)
            # File is in static directory, construct URL directly
            static_url = f"http://localhost:8124/workspace/{file_relative_to_static}"
            msg = f"Image already in workspace directory, returning URL: {static_url}"
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

    def on_write_file_request(self, request: WriteFileRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901
        """Handle a request to write content to a file."""
        # Check for CREATE_NEW policy - not yet implemented
        if request.existing_file_policy == ExistingFilePolicy.CREATE_NEW:
            msg = "CREATE_NEW policy not yet implemented"
            logger.error(msg)
            return WriteFileResultFailure(
                failure_reason=FileIOFailureReason.IO_ERROR,
                result_details=msg,
            )

        # Resolve file path
        try:
            file_path = self._resolve_file_path(request.file_path, workspace_only=False)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid path: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Get normalized path for file operations (handles Windows long paths)
        normalized_path = self.normalize_path_for_platform(file_path)

        # Check if path is a directory (must check before attempting to write)
        try:
            if Path(normalized_path).is_dir():
                msg = f"Path is a directory, not a file: {file_path}"
                logger.error(msg)
                return WriteFileResultFailure(failure_reason=FileIOFailureReason.IS_DIRECTORY, result_details=msg)
        except OSError as e:
            msg = f"Error checking if path is directory {file_path}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Check existing file policy (only if not appending)
        if not request.append and request.existing_file_policy == ExistingFilePolicy.FAIL:
            try:
                # Use os.path.exists with normalized path to handle Windows long paths
                if os.path.exists(normalized_path):  # noqa: PTH110
                    msg = f"File exists and existing_file_policy is FAIL: {file_path}"
                    logger.error(msg)
                    return WriteFileResultFailure(
                        failure_reason=FileIOFailureReason.POLICY_NO_OVERWRITE,
                        result_details=msg,
                    )
            except OSError as e:
                msg = f"Error checking if file exists {file_path}: {e}"
                logger.error(msg)
                return WriteFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Check and create parent directory if needed
        parent_normalized = self.normalize_path_for_platform(file_path.parent)
        try:
            if not os.path.exists(parent_normalized):  # noqa: PTH110
                if not request.create_parents:
                    msg = f"Parent directory does not exist and create_parents is False: {file_path.parent}"
                    logger.error(msg)
                    return WriteFileResultFailure(
                        failure_reason=FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS,
                        result_details=msg,
                    )

                # Create parent directories using os.makedirs to handle Windows long paths
                os.makedirs(parent_normalized, exist_ok=True)  # noqa: PTH103
        except PermissionError as e:
            msg = f"Permission denied creating parent directory {file_path.parent}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(
                failure_reason=FileIOFailureReason.PERMISSION_DENIED,
                result_details=msg,
            )
        except OSError as e:
            msg = f"Error creating parent directory {file_path.parent}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Write file content
        try:
            bytes_written = self._write_file_content(
                normalized_path, request.content, request.encoding, append=request.append
            )
        except PermissionError as e:
            msg = f"Permission denied writing to file {file_path}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except IsADirectoryError:
            msg = f"Path is a directory, not a file: {file_path}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.IS_DIRECTORY, result_details=msg)
        except UnicodeEncodeError as e:
            msg = f"Encoding error writing to file {file_path}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.ENCODING_ERROR, result_details=msg)
        except OSError as e:
            # Check for disk full
            if "No space left" in str(e) or "Disk full" in str(e):
                msg = f"Disk full writing to file {file_path}: {e}"
                logger.error(msg)
                return WriteFileResultFailure(failure_reason=FileIOFailureReason.DISK_FULL, result_details=msg)

            msg = f"I/O error writing to file {file_path}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error writing to file {file_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return WriteFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH - Only reached if no exceptions occurred
        return WriteFileResultSuccess(
            final_file_path=str(file_path),
            bytes_written=bytes_written,
            result_details=f"File written successfully: {file_path}",
        )

    def _copy_file(self, src_path: Path, dest_path: Path) -> int:
        """Copy a single file from source to destination with platform path normalization.

        Args:
            src_path: Source file path (Path object)
            dest_path: Destination file path (Path object)

        Returns:
            Number of bytes copied

        Raises:
            OSError: If copy operation fails
            PermissionError: If permission denied
        """
        # Normalize both paths for platform (handles Windows long paths)
        src_normalized = self.normalize_path_for_platform(src_path)
        dest_normalized = self.normalize_path_for_platform(dest_path)

        # Copy file preserving metadata
        shutil.copy2(src_normalized, dest_normalized)

        # Return size of copied file
        return os.path.getsize(src_normalized)  # noqa: PTH202

    def _write_file_content(self, normalized_path: str, content: str | bytes, encoding: str, *, append: bool) -> int:
        """Write content to a file and return bytes written.

        Args:
            normalized_path: Normalized path string (with Windows long path prefix if needed)
            content: Content to write (str for text, bytes for binary)
            encoding: Text encoding (ignored for bytes)
            append: If True, append to file; if False, overwrite

        Returns:
            Number of bytes written
        """
        # Determine mode based on content type and append flag
        if isinstance(content, bytes):
            mode = "ab" if append else "wb"
            # Use open() instead of Path.open() to support Windows long paths with \\?\ prefix
            with open(normalized_path, mode) as f:  # noqa: PTH123
                f.write(content)
            return len(content)

        # Text content
        mode = "a" if append else "w"
        # Use open() instead of Path.open() to support Windows long paths with \\?\ prefix
        with open(normalized_path, mode, encoding=encoding) as f:  # noqa: PTH123
            f.write(content)
        # Return byte count for text (encoded size)
        return len(content.encode(encoding))

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

    def on_create_file_request(self, request: CreateFileRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, C901
        """Handle a request to create a file or directory."""
        # Get the full path
        try:
            full_path_str = request.get_full_path()
        except ValueError as e:
            msg = f"Invalid path specification: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Determine if path is absolute (not constrained to workspace)
        is_absolute = Path(full_path_str).is_absolute()

        # If workspace_only is True and path is absolute, it's outside workspace
        if request.workspace_only and is_absolute:
            msg = f"Absolute path is outside workspace: {full_path_str}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Resolve path - if absolute, use as-is; if relative, align to workspace
        if is_absolute:
            file_path = self.resolve_path_safely(Path(full_path_str))
        else:
            file_path = self.resolve_path_safely(self._get_workspace_path() / full_path_str)

        # Check if it already exists - warn but treat as success
        if file_path.exists():
            msg = f"Path already exists: {file_path}"
            return CreateFileResultSuccess(
                created_path=str(file_path), result_details=ResultDetails(message=msg, level=logging.WARNING)
            )

        # Create parent directories if needed
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            msg = f"Permission denied creating parent directory for {file_path}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            msg = f"I/O error creating parent directory for {file_path}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Create file or directory
        try:
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
        except PermissionError as e:
            msg = f"Permission denied creating {file_path}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            # Check for disk full
            if "No space left" in str(e) or "Disk full" in str(e):
                msg = f"Disk full creating {file_path}: {e}"
                logger.error(msg)
                return CreateFileResultFailure(failure_reason=FileIOFailureReason.DISK_FULL, result_details=msg)

            msg = f"I/O error creating {file_path}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error creating {file_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return CreateFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH
        return CreateFileResultSuccess(
            created_path=str(file_path),
            result_details=f"{'Directory' if request.is_directory else 'File'} created successfully at {file_path}",
        )

    def on_rename_file_request(self, request: RenameFileRequest) -> ResultPayload:  # noqa: PLR0911, C901
        """Handle a request to rename a file or directory."""
        # Resolve and validate paths
        try:
            old_path = self._resolve_file_path(request.old_path, workspace_only=request.workspace_only is True)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid source path: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        try:
            new_path = self._resolve_file_path(request.new_path, workspace_only=request.workspace_only is True)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid destination path: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if old path exists
        if not old_path.exists():
            msg = f"Source path does not exist: {old_path}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)

        # Check if new path already exists
        if new_path.exists():
            msg = f"Destination path already exists: {new_path}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check workspace constraints for both paths
        is_old_in_workspace, _ = self._validate_workspace_path(old_path)
        is_new_in_workspace, _ = self._validate_workspace_path(new_path)

        if request.workspace_only and (not is_old_in_workspace or not is_new_in_workspace):
            msg = f"One or both paths are outside workspace: {old_path} -> {new_path}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Create parent directories for new path if needed
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            msg = f"Permission denied creating parent directory for {new_path}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            msg = f"I/O error creating parent directory for {new_path}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Perform the rename operation
        try:
            old_path.rename(new_path)
        except PermissionError as e:
            msg = f"Permission denied renaming {old_path} to {new_path}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            msg = f"I/O error renaming {old_path} to {new_path}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error renaming {old_path} to {new_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return RenameFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH
        details = f"Renamed: {old_path} -> {new_path}"
        return RenameFileResultSuccess(
            old_path=str(old_path),
            new_path=str(new_path),
            result_details=ResultDetails(message=details, level=logging.INFO),
        )

    def on_copy_file_request(self, request: CopyFileRequest) -> ResultPayload:  # noqa: PLR0911, C901
        """Handle a request to copy a single file."""
        # Resolve source path
        try:
            source_path = self._resolve_file_path(request.source_path, workspace_only=False)
            source_normalized = self.normalize_path_for_platform(source_path)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid source path: {e}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if source exists
        if not Path(source_normalized).exists():
            msg = f"Source file does not exist: {source_path}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)

        # Check if source is a file (not a directory)
        if not Path(source_normalized).is_file():
            msg = f"Source path is not a file: {source_path}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Resolve destination path
        try:
            destination_path = self._resolve_file_path(request.destination_path, workspace_only=False)
            dest_normalized = self.normalize_path_for_platform(destination_path)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid destination path: {e}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if destination already exists (unless overwrite is True)
        if Path(dest_normalized).exists() and not request.overwrite:
            msg = f"Destination file already exists: {destination_path}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Create parent directory if it doesn't exist
        dest_parent = Path(dest_normalized).parent
        if not dest_parent.exists():
            try:
                dest_parent.mkdir(parents=True)
            except PermissionError as e:
                msg = f"Permission denied creating parent directory {dest_parent}: {e}"
                logger.error(msg)
                return CopyFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
            except OSError as e:
                msg = f"I/O error creating parent directory {dest_parent}: {e}"
                logger.error(msg)
                return CopyFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)

        # Copy the file
        try:
            bytes_copied = self._copy_file(source_path, destination_path)
        except PermissionError as e:
            msg = f"Permission denied copying {source_path} to {destination_path}: {e}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            if "No space left" in str(e) or "Disk full" in str(e):
                msg = f"Disk full copying {source_path} to {destination_path}: {e}"
                logger.error(msg)
                return CopyFileResultFailure(failure_reason=FileIOFailureReason.DISK_FULL, result_details=msg)

            msg = f"I/O error copying {source_path} to {destination_path}: {e}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error copying {source_path} to {destination_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return CopyFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH
        return CopyFileResultSuccess(
            source_path=str(source_path),
            destination_path=str(destination_path),
            bytes_copied=bytes_copied,
            result_details=f"File copied successfully: {source_path} -> {destination_path}",
        )

    @staticmethod
    def remove_readonly(func, path, excinfo) -> None:  # noqa: ANN001, ARG004
        """Handles read-only files and long paths on Windows during shutil.rmtree.

        https://stackoverflow.com/a/50924863
        """
        if not GriptapeNodes.OSManager().is_windows():
            return

        long_path = Path(GriptapeNodes.OSManager().normalize_path_for_platform(Path(path)))

        try:
            Path.chmod(long_path, stat.S_IWRITE)
            func(long_path)
        except Exception as e:
            console.print(f"[red]Error removing read-only file: {path}[/red]")
            console.print(f"[red]Details: {e}[/red]")
            raise

    async def on_delete_file_request(self, request: DeleteFileRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, C901
        """Handle a request to delete a file or directory."""
        # FAILURE CASES FIRST (per CLAUDE.md)

        # Validate exactly one of path or file_entry provided and determine path to delete
        if request.path is not None and request.file_entry is not None:
            msg = "Attempted to delete file with both path and file_entry. Failed due to invalid parameters"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        if request.path is not None:
            path_to_delete = request.path
        elif request.file_entry is not None:
            path_to_delete = request.file_entry.path
        else:
            msg = "Attempted to delete file with neither path nor file_entry. Failed due to invalid parameters"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Resolve and validate path
        try:
            resolved_path = self._resolve_file_path(path_to_delete, workspace_only=request.workspace_only is True)
        except (ValueError, RuntimeError) as e:
            msg = f"Attempted to delete file at path {path_to_delete}. Failed due to invalid path: {e}"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if path exists
        if not resolved_path.exists():
            msg = f"Attempted to delete file at path {path_to_delete}. Failed due to path not found"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)

        # Determine if this is a directory
        is_directory = resolved_path.is_dir()

        # Collect all paths that will be deleted (for reporting)
        if is_directory:
            # Collect all file and directory paths before deletion
            deleted_paths = [str(item) for item in resolved_path.rglob("*")]
            deleted_paths.append(str(resolved_path))
        else:
            deleted_paths = [str(resolved_path)]

        # Perform deletion
        try:
            if is_directory:
                await aioshutil.rmtree(resolved_path, onexc=OSManager.remove_readonly)
            else:
                resolved_path.unlink()
        except PermissionError as e:
            msg = f"Attempted to delete {'directory' if is_directory else 'file'} at path {path_to_delete}. Failed due to permission denied: {e}"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            msg = f"Attempted to delete {'directory' if is_directory else 'file'} at path {path_to_delete}. Failed due to I/O error: {e}"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Attempted to delete {'directory' if is_directory else 'file'} at path {path_to_delete}. Failed due to unexpected error: {type(e).__name__}: {e}"
            return DeleteFileResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH AT END
        return DeleteFileResultSuccess(
            deleted_path=str(resolved_path),
            was_directory=is_directory,
            deleted_paths=deleted_paths,
            result_details=f"Successfully deleted {'directory' if is_directory else 'file'} at path {path_to_delete}",
        )

    def on_get_file_info_request(  # noqa: PLR0911
        self, request: GetFileInfoRequest
    ) -> GetFileInfoResultSuccess | GetFileInfoResultFailure:
        """Handle a request to get file/directory information."""
        # FAILURE CASES FIRST (per CLAUDE.md)

        # Validate path provided
        if not request.path:
            msg = "Attempted to get file info with empty path. Failed due to invalid parameters"
            return GetFileInfoResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Resolve and validate path
        try:
            resolved_path = self._resolve_file_path(request.path, workspace_only=request.workspace_only is True)
        except (ValueError, RuntimeError) as e:
            msg = f"Attempted to get file info at path {request.path}. Failed due to invalid path: {e}"
            return GetFileInfoResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if path exists - if not, return success with None (file doesn't exist)
        if not resolved_path.exists():
            msg = f"File info retrieved for path {request.path}: file does not exist"
            return GetFileInfoResultSuccess(file_entry=None, result_details=msg)

        # Get file information
        try:
            is_dir = resolved_path.is_dir()
            size = 0 if is_dir else resolved_path.stat().st_size
            modified_time = resolved_path.stat().st_mtime

            # Get MIME type for files only
            mime_type = None
            if not is_dir:
                mime_type = self._detect_mime_type(resolved_path)

            # Get path relative to workspace if within workspace
            _, file_path = self._validate_workspace_path(resolved_path)

            # Also get absolute resolved path
            absolute_resolved_path = str(resolved_path.resolve())

            file_entry = FileSystemEntry(
                name=resolved_path.name,
                path=str(file_path),
                is_dir=is_dir,
                size=size,
                modified_time=modified_time,
                mime_type=mime_type,
                absolute_path=absolute_resolved_path,
            )
        except PermissionError as e:
            msg = f"Attempted to get file info at path {request.path}. Failed due to permission denied: {e}"
            return GetFileInfoResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            msg = f"Attempted to get file info at path {request.path}. Failed due to I/O error: {e}"
            return GetFileInfoResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Attempted to get file info at path {request.path}. Failed due to unexpected error: {type(e).__name__}: {e}"
            return GetFileInfoResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH AT END
        return GetFileInfoResultSuccess(
            file_entry=file_entry,
            result_details=f"Successfully retrieved file info for path {request.path}",
        )

    def _validate_copy_tree_paths(
        self, source_str: str, dest_str: str, *, dirs_exist_ok: bool
    ) -> CopyTreeValidationResult | CopyTreeResultFailure:
        """Validate and normalize source and destination paths for copy tree operation.

        Returns:
            CopyTreeValidationResult on success, CopyTreeResultFailure on validation failure
        """
        # Resolve and normalize source path
        try:
            source_path = self._resolve_file_path(source_str, workspace_only=False)
            source_normalized = self.normalize_path_for_platform(source_path)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid source path: {e}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if source exists
        if not Path(source_normalized).exists():
            msg = f"Source path does not exist: {source_path}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.FILE_NOT_FOUND, result_details=msg)

        # Check if source is a directory
        if not Path(source_normalized).is_dir():
            msg = f"Source path is not a directory: {source_path}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Resolve and normalize destination path
        try:
            destination_path = self._resolve_file_path(dest_str, workspace_only=False)
            dest_normalized = self.normalize_path_for_platform(destination_path)
        except (ValueError, RuntimeError) as e:
            msg = f"Invalid destination path: {e}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        # Check if destination already exists (unless dirs_exist_ok is True)
        if Path(dest_normalized).exists() and not dirs_exist_ok:
            msg = f"Destination path already exists: {destination_path}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.INVALID_PATH, result_details=msg)

        return CopyTreeValidationResult(
            source_normalized=source_normalized,
            dest_normalized=dest_normalized,
            source_path=source_path,
            destination_path=destination_path,
        )

    def _copy_directory_tree(  # noqa: PLR0912, C901
        self,
        source_normalized: str,
        dest_normalized: str,
        *,
        symlinks: bool,
        ignore_dangling_symlinks: bool,
        ignore_patterns: list[str] | None = None,
    ) -> CopyTreeStats:
        """Copy directory tree from source to destination.

        Args:
            source_normalized: Normalized source path
            dest_normalized: Normalized destination path
            symlinks: If True, copy symbolic links as links
            ignore_dangling_symlinks: If True, ignore dangling symlinks
            ignore_patterns: List of glob patterns to ignore (e.g., ["__pycache__", "*.pyc"])

        Returns:
            CopyTreeStats with files copied and bytes copied

        Raises:
            OSError: If copy operation fails
            PermissionError: If permission denied
        """
        from fnmatch import fnmatch

        files_copied = 0
        total_bytes_copied = 0
        ignore_patterns = ignore_patterns or []

        def should_ignore(name: str) -> bool:
            """Check if a file/directory name matches any ignore pattern."""
            return any(fnmatch(name, pattern) for pattern in ignore_patterns)

        # Create destination directory if it doesn't exist
        dest_path_obj = Path(dest_normalized)
        if not dest_path_obj.exists():
            dest_path_obj.mkdir(parents=True)

        # Walk through source directory and copy files/directories
        for root, dirs, files in os.walk(source_normalized):
            # Calculate relative path from source
            root_path = Path(root)
            source_path_obj = Path(source_normalized)
            rel_path = root_path.relative_to(source_path_obj)

            # Create corresponding directory in destination
            if str(rel_path) != ".":
                dest_dir = dest_path_obj / rel_path
            else:
                dest_dir = dest_path_obj

            # Filter out ignored directories and create remaining ones
            dirs_to_remove = []
            for dir_name in dirs:
                if should_ignore(dir_name):
                    dirs_to_remove.append(dir_name)
                    continue

                src_dir = root_path / dir_name
                dst_dir = dest_dir / dir_name

                # Handle symlinks if requested
                if src_dir.is_symlink():
                    if symlinks:
                        link_target = src_dir.readlink()
                        dst_dir.symlink_to(link_target)
                    continue

                if not dst_dir.exists():
                    dst_dir.mkdir(parents=True)

            # Remove ignored directories from dirs list to prevent os.walk from descending into them
            for dir_name in dirs_to_remove:
                dirs.remove(dir_name)

            # Copy files
            for file_name in files:
                # Skip ignored files
                if should_ignore(file_name):
                    continue

                src_file = root_path / file_name
                dst_file = dest_dir / file_name

                # Handle symlinks if requested
                if src_file.is_symlink():
                    if symlinks:
                        try:
                            link_target = src_file.readlink()
                            dst_file.symlink_to(link_target)
                        except OSError:
                            if not ignore_dangling_symlinks:
                                raise
                    continue

                # Copy file
                bytes_copied = self._copy_file(src_file, dst_file)
                files_copied += 1
                total_bytes_copied += bytes_copied

        return CopyTreeStats(files_copied=files_copied, total_bytes_copied=total_bytes_copied)

    def on_copy_tree_request(self, request: CopyTreeRequest) -> ResultPayload:
        """Handle a request to copy a directory tree."""
        # Validate paths
        validation_result = self._validate_copy_tree_paths(
            request.source_path,
            request.destination_path,
            dirs_exist_ok=request.dirs_exist_ok,
        )

        if isinstance(validation_result, CopyTreeResultFailure):
            return validation_result

        source_normalized = validation_result.source_normalized
        dest_normalized = validation_result.dest_normalized
        source_path = validation_result.source_path
        destination_path = validation_result.destination_path

        # Copy directory tree
        try:
            stats = self._copy_directory_tree(
                source_normalized,
                dest_normalized,
                symlinks=request.symlinks,
                ignore_dangling_symlinks=request.ignore_dangling_symlinks,
                ignore_patterns=request.ignore_patterns,
            )
        except PermissionError as e:
            msg = f"Permission denied copying {source_path} to {destination_path}: {e}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.PERMISSION_DENIED, result_details=msg)
        except OSError as e:
            if "No space left" in str(e) or "Disk full" in str(e):
                msg = f"Disk full copying {source_path} to {destination_path}: {e}"
                logger.error(msg)
                return CopyTreeResultFailure(failure_reason=FileIOFailureReason.DISK_FULL, result_details=msg)

            msg = f"I/O error copying {source_path} to {destination_path}: {e}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.IO_ERROR, result_details=msg)
        except Exception as e:
            msg = f"Unexpected error copying {source_path} to {destination_path}: {type(e).__name__}: {e}"
            logger.error(msg)
            return CopyTreeResultFailure(failure_reason=FileIOFailureReason.UNKNOWN, result_details=msg)

        # SUCCESS PATH
        return CopyTreeResultSuccess(
            source_path=str(source_path),
            destination_path=str(destination_path),
            files_copied=stats.files_copied,
            total_bytes_copied=stats.total_bytes_copied,
            result_details=f"Directory tree copied successfully: {source_path} -> {destination_path}",
        )

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        """Handle app initialization complete event by registering system resources."""
        self._register_system_resources()

    # NEW Resource Management Methods
    def _register_system_resources(self) -> None:
        """Register OS and CPU resource types with ResourceManager and create system instances."""
        self._attempt_generate_os_resources()
        self._attempt_generate_cpu_resources()

    def _attempt_generate_os_resources(self) -> None:
        """Register OS resource type and create system OS instance if successful."""
        # Register OS resource type
        os_resource_type = OSResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=os_resource_type)
        result = GriptapeNodes.handle_request(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error("Attempted to register OS resource type. Failed due to resource type registration failure")
            return

        logger.debug("Successfully registered OS resource type")
        # Registration successful, now create instance
        self._create_system_os_instance()

    def _attempt_generate_cpu_resources(self) -> None:
        """Register CPU resource type and create system CPU instance if successful."""
        # Register CPU resource type
        cpu_resource_type = CPUResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=cpu_resource_type)
        result = GriptapeNodes.handle_request(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error("Attempted to register CPU resource type. Failed due to resource type registration failure")
            return

        logger.debug("Successfully registered CPU resource type")
        # Registration successful, now create instance
        self._create_system_cpu_instance()

    def _create_system_os_instance(self) -> None:
        """Create system OS instance."""
        os_capabilities = {
            "platform": self._get_platform_name(),
            "arch": self._get_architecture(),
            "version": self._get_platform_version(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="OSResourceType", capabilities=os_capabilities
        )
        result = GriptapeNodes.handle_request(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system OS resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system OS instance: %s", result.instance_id)

    def _create_system_cpu_instance(self) -> None:
        """Create system CPU instance."""
        cpu_capabilities = {
            "cores": os.cpu_count() or 1,
            "architecture": self._get_architecture(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="CPUResourceType", capabilities=cpu_capabilities
        )
        result = GriptapeNodes.handle_request(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system CPU resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system CPU instance: %s", result.instance_id)

    def _get_platform_name(self) -> str:
        """Get platform name using existing sys.platform detection."""
        if self.is_windows():
            return "windows"
        if self.is_mac():
            return "darwin"
        if self.is_linux():
            return "linux"
        return sys.platform

    def _get_architecture(self) -> str:
        """Get system architecture."""
        try:
            return os.uname().machine.lower()
        except AttributeError:
            # Windows doesn't have os.uname(), fallback to environment variable
            return os.environ.get("PROCESSOR_ARCHITECTURE", "unknown").lower()

    def _get_platform_version(self) -> str:
        """Get platform version."""
        try:
            return os.uname().release
        except AttributeError:
            # Windows doesn't have os.uname(), return basic platform info
            return sys.platform
