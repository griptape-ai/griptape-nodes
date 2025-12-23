import base64
import logging
import mimetypes
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import aioshutil
import portalocker
from binaryornot.check import is_binary
from rich.console import Console

from griptape_nodes.common.macro_parser import MacroResolutionError, MacroResolutionFailure, ParsedMacro
from griptape_nodes.common.macro_parser.exceptions import MacroResolutionFailureReason
from griptape_nodes.common.macro_parser.formats import NumericPaddingFormat
from griptape_nodes.common.macro_parser.resolution import partial_resolve
from griptape_nodes.common.macro_parser.segments import ParsedStaticValue, ParsedVariable
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
    GetNextUnusedFilenameRequest,
    GetNextUnusedFilenameResultFailure,
    GetNextUnusedFilenameResultSuccess,
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
from griptape_nodes.retained_mode.events.project_events import MacroPath
from griptape_nodes.retained_mode.events.resource_events import (
    CreateResourceInstanceRequest,
    CreateResourceInstanceResultSuccess,
    RegisterResourceTypeRequest,
    RegisterResourceTypeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.resource_types.compute_resource import ComputeBackend, ComputeResourceType
from griptape_nodes.retained_mode.managers.resource_types.cpu_resource import CPUResourceType
from griptape_nodes.retained_mode.managers.resource_types.os_resource import Architecture, OSResourceType, Platform

console = Console()

# Windows MAX_PATH limit - paths longer than this need \\?\ prefix
WINDOWS_MAX_PATH = 260

# Maximum number of indexed candidates to try when CREATE_NEW policy is used
MAX_INDEXED_CANDIDATES = 1000


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


class FileWriteAttemptResult(NamedTuple):
    """Result of attempting to write a file.

    Possible outcomes:
    - Success: bytes_written is set, failure_reason and error_message are None
    - Continue: all fields are None (file exists/locked but caller wants to continue)
    - Failure: failure_reason and error_message are set, bytes_written is None
    """

    bytes_written: int | None
    failure_reason: FileIOFailureReason | None
    error_message: str | None


@dataclass
class CopyTreeValidationResult:
    """Result from validating copy tree paths."""

    source_normalized: str
    dest_normalized: str
    source_path: Path
    destination_path: Path


class FilenameParts(NamedTuple):
    """Components of a filename for suffix injection strategy.

    Attributes:
        directory: Parent directory path
        basename: Filename without extension or suffix
        extension: File extension including dot (e.g., ".png"), empty string if no extension
    """

    directory: Path
    basename: str
    extension: str


class FilePathValidationError(Exception):
    """Raised when file path validation fails before write operation.

    This exception is raised by validation methods when a file path
    is unsuitable for writing due to policy violations, missing parent
    directories, or invalid path types.
    """

    def __init__(
        self,
        message: str,
        reason: FileIOFailureReason,
    ) -> None:
        """Initialize FilePathValidationError.

        Args:
            message: Human-readable error message
            reason: Classification of why validation failed
        """
        super().__init__(message)
        self.reason = reason


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

            # Store event_manager for direct access during resource registration
            self._event_manager = event_manager

            # Register system resources immediately using the event_manager directly
            # This must happen before libraries are loaded so they can check requirements
            # We use event_manager directly to avoid singleton recursion issues
            self._register_system_resources_direct()

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

    def _resolve_macro_path_to_string(self, macro_path: MacroPath) -> str | MacroResolutionFailure:
        """Resolve MacroPath to string, handling missing variables.

        Args:
            macro_path: MacroPath containing parsed macro and variables

        Returns:
            str: Successfully resolved path string
            MacroResolutionFailure: Details about resolution failure (missing variables, etc.)

        Examples:
            # Success case
            macro_path = MacroPath(ParsedMacro("{outputs}/file.png"), {"outputs": "/path"})
            result = self._resolve_macro_path_to_string(macro_path)
            # Returns: "/path/file.png"

            # Missing variable case
            macro_path = MacroPath(ParsedMacro("{outputs}/{frame}.png"), {"outputs": "/path"})
            result = self._resolve_macro_path_to_string(macro_path)
            # Returns: MacroResolutionFailure(missing_variables={"frame"}, ...)
        """
        secrets_manager = GriptapeNodes.SecretsManager()

        try:
            return macro_path.parsed_macro.resolve(macro_path.variables, secrets_manager)
        except MacroResolutionError as e:
            return MacroResolutionFailure(
                failure_reason=e.failure_reason or MacroResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                variable_name=e.variable_name,
                missing_variables=e.missing_variables,
                error_details=str(e),
            )

    def _validate_file_path_for_write(
        self,
        file_path: Path,
        *,
        check_not_exists: bool,
        create_parents: bool,
    ) -> None:
        """Validate file path is suitable for writing.

        Checks:
        - Path is not a directory
        - File doesn't exist (only if check_not_exists=True, for FAIL policy)
        - Parent directory exists OR create_parents=True

        Args:
            file_path: Path to validate
            check_not_exists: If True, fail if file already exists (FAIL policy)
            create_parents: If True, parent creation allowed (policy check only)

        Raises:
            FilePathValidationError: If validation fails, contains reason and message

        Examples:
            # FAIL policy: check file doesn't exist
            try:
                self._validate_file_path_for_write(path, check_not_exists=True, create_parents=True)
            except FilePathValidationError as e:
                # Handle validation failure: e.reason, str(e)
                pass

            # OVERWRITE policy: existence OK
            self._validate_file_path_for_write(path, check_not_exists=False, create_parents=False)
        """
        normalized_path = self.normalize_path_for_platform(file_path)

        # Check if path is a directory
        try:
            if Path(normalized_path).is_dir():
                raise FilePathValidationError(
                    message=f"Path is a directory, not a file: {file_path}",
                    reason=FileIOFailureReason.IS_DIRECTORY,
                )
        except OSError as e:
            raise FilePathValidationError(
                message=f"Error checking if path is directory {file_path}: {e}",
                reason=FileIOFailureReason.IO_ERROR,
            ) from e

        # Check if file exists (FAIL policy only)
        if check_not_exists:
            try:
                if Path(normalized_path).exists():
                    raise FilePathValidationError(
                        message=f"File exists and existing_file_policy is FAIL: {file_path}",
                        reason=FileIOFailureReason.POLICY_NO_OVERWRITE,
                    )
            except OSError as e:
                raise FilePathValidationError(
                    message=f"Error checking if file exists {file_path}: {e}",
                    reason=FileIOFailureReason.IO_ERROR,
                ) from e

        # Check parent directory exists or can be created
        parent_normalized = self.normalize_path_for_platform(file_path.parent)
        try:
            if not Path(parent_normalized).exists() and not create_parents:
                raise FilePathValidationError(
                    message=f"Parent directory does not exist and create_parents is False: {file_path.parent}",
                    reason=FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS,
                )
        except OSError as e:
            raise FilePathValidationError(
                message=f"Error checking parent directory {file_path.parent}: {e}",
                reason=FileIOFailureReason.IO_ERROR,
            ) from e

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

    @staticmethod
    def strip_surrounding_quotes(path_str: str) -> str:
        """Strip surrounding quotes only if they match (from 'Copy as Pathname').

        Args:
            path_str: The path string to process

        Returns:
            Path string with surrounding quotes removed if present
        """
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            return path_str[1:-1]
        return path_str

    def sanitize_path_string(self, path: str | Path | Any) -> str | Any:
        r"""Clean path strings by removing newlines, carriage returns, shell escapes, and quotes.

        This method handles multiple path cleaning concerns:
        1. Removes newlines/carriage returns that cause WinError 123 on Windows
           (from merge_texts nodes accidentally adding newlines between path components)
        2. Removes shell escape characters and quotes (from macOS Finder 'Copy as Pathname')
        3. Strips leading/trailing whitespace

        Handles macOS Finder's 'Copy as Pathname' format which escapes
        spaces, apostrophes, and other special characters with backslashes.
        Only removes backslashes before shell-special characters to avoid
        breaking Windows paths like C:\Users\file.txt.

        Examples:
            macOS Finder paths:
                "/Downloads/Dragon\'s\ Curse/screenshot.jpg"
                -> "/Downloads/Dragon's Curse/screenshot.jpg"

                "/Test\ Images/Level\ 1\ -\ Knight\'s\ Quest/file.png"
                -> "/Test Images/Level 1 - Knight's Quest/file.png"

            Quoted paths:
                '"/path/with spaces/file.txt"'
                -> "/path/with spaces/file.txt"

            Windows paths with newlines:
                "C:\\Users\\file\\n\\n.txt"
                -> "C:\\Users\\file.txt"

            Windows extended-length paths:
                r"\\?\C:\Very\ Long\ Path\file.txt"
                -> r"\\?\C:\Very Long Path\file.txt"

            Path objects:
                Path("/path/to/file")
                -> "/path/to/file"

        Args:
            path: Path string, Path object, or any other type to sanitize

        Returns:
            Sanitized path string, or original value if not a string/Path
        """
        # Convert Path objects to strings
        if isinstance(path, Path):
            path = str(path)

        if not isinstance(path, str):
            return path

        # First, strip surrounding quotes
        path_str = OSManager.strip_surrounding_quotes(path)

        # Handle Windows extended-length paths (\\?\...) specially
        # These are used for paths longer than 260 characters on Windows
        # We need to sanitize the path part but preserve the prefix
        extended_length_prefix = ""
        if path_str.startswith("\\\\?\\"):
            extended_length_prefix = "\\\\?\\"
            path_str = path_str[4:]  # Remove prefix temporarily

        # Remove shell escape characters (backslashes before special chars only)
        # Matches: space ' " ( ) { } [ ] & | ; < > $ ` ! * ? /
        # Does NOT match: \U \t \f etc in Windows paths like C:\Users
        path_str = re.sub(r"\\([ '\"(){}[\]&|;<>$`!*?/])", r"\1", path_str)

        # Remove newlines and carriage returns from anywhere in the path
        path_str = path_str.replace("\n", "").replace("\r", "")

        # Strip leading/trailing whitespace
        path_str = path_str.strip()

        # Restore extended-length prefix if it was present
        if extended_length_prefix:
            path_str = extended_length_prefix + path_str

        return path_str

    def normalize_path_for_platform(self, path: Path) -> str:
        r"""Convert Path to string with Windows long path support if needed.

        Windows has a 260 character path limit (MAX_PATH). Paths longer than this
        need the \\?\ prefix to work correctly. This method transparently adds
        the prefix when needed on Windows.

        Also cleans paths to remove newlines/carriage returns that cause Windows errors.

        Note: This method assumes the path exists or will exist. For non-existent
        paths that need cross-platform normalization, use resolve_path_safely() first.

        Args:
            path: Path object to convert to string

        Returns:
            String representation of path, cleaned of newlines/carriage returns,
            with Windows long path prefix if needed
        """
        path_str = str(path.resolve())

        # Clean path to remove newlines/carriage returns, shell escapes, and quotes
        # This handles cases where merge_texts nodes accidentally add newlines between path components
        path_str = self.sanitize_path_string(path_str)

        # Windows long path handling (paths > WINDOWS_MAX_PATH chars need \\?\ prefix)
        if self.is_windows() and len(path_str) >= WINDOWS_MAX_PATH and not path_str.startswith("\\\\?\\"):
            # UNC paths (\\server\share) need \\?\UNC\ prefix
            if path_str.startswith("\\\\"):
                return f"\\\\?\\UNC\\{path_str[2:]}"
            # Regular paths need \\?\ prefix
            return f"\\\\?\\{path_str}"

        return path_str

    # ============================================================================
    # CREATE_NEW File Collision Policy - Helper Methods
    # ============================================================================

    def _identify_index_variable(
        self, parsed_macro: ParsedMacro, variables: dict[str, str | int]
    ) -> ParsedVariable | None:
        """Identify which variable should be used for auto-incrementing.

        Analyzes the macro to find unresolved required variables. Returns None if all
        variables are resolved (fallback to suffix injection), returns ParsedVariable
        if exactly one unresolved variable exists, raises error if multiple unresolved.

        Args:
            parsed_macro: Parsed macro template
            variables: Variable values provided by user

        Returns:
            ParsedVariable if exactly one unresolved variable exists,
            None if all variables resolved (use suffix injection fallback)

        Raises:
            ValueError: If multiple unresolved required variables exist (ambiguous)

        Examples:
            Template: "{outputs}/frame_{frame_num:05}.png"
            Variables: {"outputs": "/path"}
            → Returns ParsedVariable with name="frame_num", format_specs=[NumericPaddingFormat(5)]

            Template: "{outputs}/render.png"
            Variables: {"outputs": "/path"}
            → Returns None (use suffix injection)

            Template: "{outputs}/{batch}/frame_{frame_num}.png"
            Variables: {"outputs": "/path"}
            → Raises ValueError (batch and frame_num both unresolved)
        """
        # Partially resolve to identify unresolved variables
        secrets_manager = GriptapeNodes.SecretsManager()
        partial = partial_resolve(parsed_macro.template, parsed_macro.segments, variables, secrets_manager)

        # Get unresolved variables (optional variables already filtered out)
        unresolved = partial.get_unresolved_variables()

        if len(unresolved) == 0:
            # All variables resolved - use suffix injection fallback
            return None

        if len(unresolved) > 1:
            # Multiple unresolved - ambiguous which to auto-increment
            unresolved_names = [var.info.name for var in unresolved]
            msg = (
                f"CREATE_NEW policy requires at most one unresolved variable for auto-increment, "
                f"found {len(unresolved)}: {', '.join(unresolved_names)}"
            )
            raise ValueError(msg)

        # Exactly one unresolved variable - return it directly
        return unresolved[0]

    def _build_glob_pattern_from_partially_resolved(self, partial_segments: list, index_var_name: str) -> str:
        """Build glob pattern by replacing index variable with wildcards.

        Takes partially resolved segments (from partial_resolve) and replaces the index
        variable with wildcard patterns based on its format specs.

        Args:
            partial_segments: Segments from PartiallyResolvedMacro.segments
            index_var_name: Name of the variable to replace with wildcards

        Returns:
            Glob pattern string with wildcards for index variable

        Examples:
            Segments for "/path/frame_{index:05}.png" with index unresolved:
            → "/path/frame_?????.png"

            Segments for "/path/batch_{index:03}_frame_{index:05}.png":
            → "/path/batch_???_frame_?????.png"

            Segments for "/path/frame_{index}.png" (no padding):
            → "/path/frame_*.png"
        """
        pattern_parts = []

        for segment in partial_segments:
            if isinstance(segment, ParsedStaticValue):
                # Keep static text as-is
                pattern_parts.append(segment.text)
            elif isinstance(segment, ParsedVariable):
                if segment.info.name == index_var_name:
                    # Replace index variable with wildcards based on padding
                    has_padding = False
                    for format_spec in segment.format_specs:
                        if isinstance(format_spec, NumericPaddingFormat):
                            # Use exact number of wildcards for padding width
                            pattern_parts.append("?" * format_spec.width)
                            has_padding = True
                            break

                    if not has_padding:
                        # No padding format - match any number of digits
                        pattern_parts.append("*")
                else:
                    # This shouldn't happen - all non-index variables should be resolved
                    msg = f"Unexpected unresolved variable '{segment.info.name}' when building glob pattern"
                    raise ValueError(msg)

        return "".join(pattern_parts)

    def _extract_index_from_filename(
        self, filename: str, parsed_macro: ParsedMacro, index_var_name: str, variables: dict[str, str | int]
    ) -> int | None:
        """Extract index value from a filename by reverse-matching against macro.

        Uses the macro's extract_variables() method to parse the filename and extract
        the index variable value.

        Args:
            filename: Filename to parse (e.g., "frame_00123.png")
            parsed_macro: Original parsed macro template
            index_var_name: Name of the index variable to extract
            variables: Known variable values (for partial matching)

        Returns:
            Integer index value if successfully extracted, None if filename doesn't match

        Examples:
            Filename: "frame_00123.png"
            Template: "{outputs}/frame_{frame_num:05}.png"
            Variables: {"outputs": "/path"}
            → Returns 123
        """
        secrets_manager = GriptapeNodes.SecretsManager()

        # Use macro's extract_variables to reverse-match
        extracted = parsed_macro.extract_variables(filename, variables, secrets_manager)

        if extracted is None:
            # Filename doesn't match template
            return None

        if index_var_name not in extracted:
            # Index variable not found in extraction
            return None

        value = extracted[index_var_name]

        # Convert to int (format_spec.reverse() should have done this already)
        if isinstance(value, int):
            return value

        # Try to parse as string
        if isinstance(value, str) and value.isdigit():
            return int(value)

        return None

    def _parse_filename_parts(self, path: Path) -> FilenameParts:
        """Parse filename into directory, basename, and extension for suffix injection.

        Args:
            path: Full file path to parse

        Returns:
            FilenameParts with directory, basename, extension

        Examples:
            /path/to/render.png → FilenameParts(Path("/path/to"), "render", ".png")
            /path/to/file → FilenameParts(Path("/path/to"), "file", "")
            /path/to/.dotfile → FilenameParts(Path("/path/to"), ".dotfile", "")
            /path/to/file.tar.gz → FilenameParts(Path("/path/to"), "file.tar", ".gz")
        """
        directory = path.parent
        filename = path.name

        # Handle dotfiles (files starting with .)
        if filename.startswith(".") and filename.count(".") == 1:
            # .dotfile with no extension
            return FilenameParts(directory=directory, basename=filename, extension="")

        # Find last dot for extension
        if "." in filename:
            last_dot = filename.rfind(".")
            basename = filename[:last_dot]
            extension = filename[last_dot:]
            return FilenameParts(directory=directory, basename=basename, extension=extension)

        # No extension
        return FilenameParts(directory=directory, basename=filename, extension="")

    def _build_suffix_glob_pattern(self, directory: Path, basename: str, extension: str) -> str:
        """Build glob pattern for suffix injection strategy.

        Args:
            directory: Parent directory
            basename: Filename without extension
            extension: File extension including dot

        Returns:
            Glob pattern string

        Examples:
            ("render", ".png") → "render_*.png"
            ("file", "") → "file_*"
        """
        if extension:
            return str(directory / f"{basename}_*{extension}")
        return str(directory / f"{basename}_*")

    def _extract_suffix_index(self, filename: str, basename: str, extension: str) -> int | None:
        """Extract numeric index from suffix in filename.

        Args:
            filename: Full filename (e.g., "render_123.png")
            basename: Expected base name (e.g., "render")
            extension: Expected extension (e.g., ".png")

        Returns:
            Integer index if found, None otherwise

        Examples:
            ("render_123.png", "render", ".png") → 123
            ("render_1.png", "render", ".png") → 1
            ("render.png", "render", ".png") → None (no suffix)
            ("other_123.png", "render", ".png") → None (different basename)
        """
        # Remove extension if present
        if extension and filename.endswith(extension):
            name_without_ext = filename[: -len(extension)]
        else:
            name_without_ext = filename

        # Check if it starts with basename
        expected_prefix = f"{basename}_"
        if not name_without_ext.startswith(expected_prefix):
            return None

        # Extract suffix after basename_
        suffix = name_without_ext[len(expected_prefix) :]

        # Try to parse as integer
        if suffix.isdigit():
            return int(suffix)

        return None

    def _convert_str_path_to_macro_with_index(self, path_str: str) -> MacroPath:
        """Convert string path to MacroPath with required {_index} variable for indexed filenames.

        This is used when the base filename (without index) is already taken.
        Converts paths like "/outputs/render.png" to template "/outputs/render_{_index}.png".

        Args:
            path_str: String path like "/outputs/render.png"

        Returns:
            MacroPath with required _index variable for indexed filenames

        Examples:
            Input: "/outputs/render.png"
            Output: MacroPath with template "/outputs/render_{_index}.png"
            Behavior: render_1.png → render_2.png → render_3.png → ...

            Input: "/outputs/file"
            Output: MacroPath with template "/outputs/file_{_index}"
            Behavior: file_1 → file_2 → file_3 → ...

        Note:
            The base filename (e.g., "render.png") should be tried first before
            using this template for indexed filenames.
        """
        path = Path(path_str)
        stem = path.stem
        suffix = path.suffix
        parent = str(path.parent)

        if suffix:
            template = f"{parent}/{stem}_{{_index}}{suffix}"
        else:
            template = f"{parent}/{stem}_{{_index}}"

        parsed_macro = ParsedMacro(template)

        return MacroPath(parsed_macro=parsed_macro, variables={})

    def _scan_for_next_available_index(
        self,
        parsed_macro: ParsedMacro,
        variables: dict[str, str | int],
        index_var: ParsedVariable,
    ) -> int | None:
        """Scan existing files and return next available index (preview only - no file creation).

        Uses fill-gaps strategy: if indices 1, 2, 4 exist, returns 3.
        If index variable is optional and base filename is free, returns None.

        This is a preview method - it ONLY scans the filesystem and returns a suggestion.
        It does NOT create any files or acquire any locks.

        Args:
            parsed_macro: Parsed macro template
            variables: Known variable values (index variable NOT included)
            index_var: The parsed variable to use for auto-incrementing

        Returns:
            Next available index (1, 2, 3...), or None if index is optional and base filename is free

        Examples:
            Optional index with base file free:
                Template: "/outputs/render{_index?:_}.png"
                Files: ["/outputs/other.png"]
                Returns: None (use base filename "/outputs/render.png")

            Optional index with base file taken:
                Template: "/outputs/render{_index?:_}.png"
                Files: ["/outputs/render.png"]
                Returns: 1 (use "/outputs/render_1.png")

            Fill gaps strategy:
                Template: "/outputs/render{_index:03}.png"
                Files: ["/outputs/render001.png", "/outputs/render002.png", "/outputs/render004.png"]
                Returns: 3 (fill the gap)

            No existing files:
                Template: "/outputs/render{_index:03}.png"
                Files: []
                Returns: 1 (start with index 1)
        """
        secrets_manager = GriptapeNodes.SecretsManager()
        index_var_name = index_var.info.name

        # Check if index variable is optional
        is_optional = not index_var.info.is_required

        if is_optional:
            # Try to resolve without the index variable to get base filename
            try:
                base_resolved = parsed_macro.resolve(variables, secrets_manager)
                base_path = Path(base_resolved)
                if not base_path.exists():
                    return None  # Use base filename (no index)
            except MacroResolutionError:
                # Cannot resolve without index - treat as required
                pass

        # Build glob pattern by partially resolving with known variables
        partial = partial_resolve(parsed_macro.template, parsed_macro.segments, variables, secrets_manager)
        glob_pattern = self._build_glob_pattern_from_partially_resolved(partial.segments, index_var_name)

        # Scan existing files matching pattern
        glob_path = Path(glob_pattern)
        if not glob_path.parent.exists():
            # Parent directory doesn't exist - start at index 1
            return 1

        existing_files = list(glob_path.parent.glob(glob_path.name))
        existing_indices = []

        for filepath in existing_files:
            filename = Path(filepath).name
            extracted_index = self._extract_index_from_filename(filename, parsed_macro, index_var_name, variables)
            if extracted_index is not None:
                existing_indices.append(extracted_index)

        if not existing_indices:
            # No existing indexed files - start at 1
            return 1

        # Sort indices to find first gap
        existing_indices.sort()

        # Find first gap starting from 1
        for i in range(1, max(existing_indices) + 1):
            if i not in existing_indices:
                return i  # Found a gap

        # No gaps - use max + 1
        return max(existing_indices) + 1

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

        # Sanitize path to handle shell escapes and quotes (e.g., from macOS Finder "Copy as Pathname")
        file_path_str = self.sanitize_path_string(file_path_str)

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

    def _is_hidden(self, dir_entry: os.DirEntry, stat_result: os.stat_result | None = None) -> bool:
        """Check if a directory entry is hidden in an OS-independent way.

        On Unix/Linux/macOS: Files are considered hidden if their name starts with a dot (.).
        On Windows: Files have a special "hidden" file attribute (FILE_ATTRIBUTE_HIDDEN).

        Args:
            dir_entry: The directory entry to check
            stat_result: Optional pre-fetched stat result (to avoid redundant stat() calls on Windows)

        Returns:
            True if the entry is hidden, False otherwise
        """
        if sys.platform == "win32":
            # Windows: Check name prefix first (fast heuristic for most hidden files)
            # Most hidden files on Windows have dot prefix, so this avoids many stat() calls
            if dir_entry.name.startswith("."):
                return True
            # For files without dot prefix, check FILE_ATTRIBUTE_HIDDEN via stat()
            if stat_result is None:
                stat_result = dir_entry.stat(follow_symlinks=False)
            return bool(stat_result.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
        # Unix/Linux/macOS: Files are hidden if name starts with dot
        return dir_entry.name.startswith(".")

    def _detect_mime_type(self, file_path: Path) -> str | None:
        """Detect MIME type for a file. Returns None for directories or if detection fails.

        Args:
            file_path: Original file path (used for is_dir() check and filename extraction)
        """
        if file_path.is_dir():
            return None

        # mimetypes.guess_type() only needs the filename, not the full path
        # Using just the filename is ~2x faster and avoids path normalization overhead
        filename = file_path.name
        try:
            mime_type, _ = mimetypes.guess_type(filename, strict=True)
        except Exception as e:
            msg = f"MIME type detection failed for {file_path} (filename: {filename}): {e}"
            logger.warning(msg)
            return "text/plain"

        if mime_type is None:
            mime_type = "text/plain"
        return mime_type

    def on_list_directory_request(self, request: ListDirectoryRequest) -> ResultPayload:  # noqa: C901, PLR0911, PLR0912, PLR0915
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

            # Cache workspace path and resolved workspace to avoid repeated lookups/resolutions
            # Only resolve workspace if we need it for relative paths or absolute paths
            need_relative_paths = request.workspace_only is True
            workspace_path = GriptapeNodes.ConfigManager().workspace_path
            if need_relative_paths or request.include_absolute_path:
                resolved_workspace = workspace_path.resolve()
            else:
                resolved_workspace = None

            entries = []
            try:
                # Pre-compute whether we need stat() calls (constant for all entries)
                need_stat_for_metadata = request.include_size or request.include_modified_time
                # On Windows, we need stat() to check FILE_ATTRIBUTE_HIDDEN when filtering hidden files
                # (only for files without dot prefix, since dot-prefix files are handled by name check)
                need_stat_for_hidden = not request.show_hidden and sys.platform == "win32"

                # Use os.scandir() instead of Path.iterdir() for better performance
                # os.scandir() is ~3.7x faster and provides cached stat info
                with os.scandir(str(directory)) as scan_iter:
                    for dir_entry in scan_iter:
                        # Initialize stat - we'll get it once if needed for hidden check and/or metadata
                        stat = None

                        # Skip hidden files if not requested (OS-independent check)
                        if not request.show_hidden:
                            # On Windows, files without dot prefix need stat() to check FILE_ATTRIBUTE_HIDDEN
                            # Get stat() once if needed (for hidden check and/or metadata)
                            if need_stat_for_hidden and not dir_entry.name.startswith("."):
                                stat = dir_entry.stat(follow_symlinks=False)

                            if self._is_hidden(dir_entry, stat_result=stat):
                                continue

                        # Apply pattern filter if specified, or create Path object if needed
                        if request.pattern is not None:
                            # Convert DirEntry to Path for pattern matching
                            entry_path_obj = Path(dir_entry.path)
                            if not entry_path_obj.match(request.pattern):
                                continue
                        elif request.include_absolute_path or request.include_mime_type or need_relative_paths:
                            # Only create Path object if we need it
                            entry_path_obj = Path(dir_entry.path)
                        else:
                            entry_path_obj = None

                        try:
                            # Get stat() if needed for metadata (reuse if we already have it from hidden check)
                            if need_stat_for_metadata and stat is None:
                                stat = dir_entry.stat(follow_symlinks=False)

                            # Only resolve entry path if we need absolute_path or relative paths
                            resolved_entry = None
                            absolute_resolved_path = ""
                            if request.include_absolute_path or need_relative_paths:
                                if entry_path_obj is None:
                                    entry_path_obj = Path(dir_entry.path)
                                resolved_entry = entry_path_obj.resolve()
                                absolute_resolved_path = str(resolved_entry) if request.include_absolute_path else ""

                            # Determine entry_path based on what we need
                            if need_relative_paths and resolved_entry is not None and resolved_workspace is not None:
                                try:
                                    relative = resolved_entry.relative_to(resolved_workspace)
                                    entry_path = relative
                                except ValueError:
                                    # Entry is outside workspace
                                    entry_path = resolved_entry
                            elif request.include_absolute_path and resolved_entry is not None:
                                entry_path = resolved_entry
                            else:
                                # Use the path from dir_entry (may be relative or absolute depending on system)
                                entry_path = dir_entry.path

                            # Only detect MIME type if requested
                            mime_type = None
                            if request.include_mime_type:
                                if entry_path_obj is None:
                                    entry_path_obj = Path(dir_entry.path)
                                # Use resolved_entry if available, otherwise just entry_path_obj
                                mime_type = self._detect_mime_type(entry_path_obj)

                            # Determine size and modified_time values
                            entry_size = 0
                            if stat and request.include_size:
                                entry_size = stat.st_size

                            entry_modified_time = 0.0
                            if stat and request.include_modified_time:
                                entry_modified_time = stat.st_mtime

                            entries.append(
                                FileSystemEntry(
                                    name=dir_entry.name,
                                    path=str(entry_path),
                                    is_dir=dir_entry.is_dir(),
                                    size=entry_size,
                                    modified_time=entry_modified_time,
                                    mime_type=mime_type,
                                    absolute_path=absolute_resolved_path,
                                )
                            )
                        except (OSError, PermissionError) as e:
                            msg = f"Could not process entry {dir_entry.name}: {e}"
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
            content, encoding = self._read_binary_file(
                file_path,
                mime_type,
                should_transform_to_thumbnail=request.should_transform_image_content_to_thumbnail,
            )

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

    def _read_binary_file(
        self, file_path: Path, mime_type: str, *, should_transform_to_thumbnail: bool
    ) -> tuple[bytes | str, None]:
        """Read file as binary, with optional thumbnail generation for images."""
        with file_path.open("rb") as f:
            content = f.read()

        if mime_type.startswith("image/") and should_transform_to_thumbnail:
            content = self._generate_thumbnail_from_image_content(content, file_path, mime_type)

        return content, None

    def _generate_thumbnail_from_image_content(self, content: bytes, file_path: Path, mime_type: str) -> str:
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

    def on_get_next_unused_filename_request(self, request: GetNextUnusedFilenameRequest) -> ResultPayload:
        """Handle a request to find the next available filename (preview only - no file creation)."""
        # Handle string paths specially: try base path first, then indexed
        if isinstance(request.file_path, str):
            # First, check if base path is available
            try:
                base_path = self._resolve_file_path(request.file_path, workspace_only=False)
            except (ValueError, RuntimeError) as e:
                msg = f"Invalid path: {e}"
                logger.error(msg)
                return GetNextUnusedFilenameResultFailure(
                    failure_reason=FileIOFailureReason.INVALID_PATH,
                    result_details=msg,
                )

            if not base_path.exists():
                # Base filename is available - use it
                return GetNextUnusedFilenameResultSuccess(
                    available_filename=str(base_path),
                    index_used=None,
                    result_details="Found available filename (no index needed)",
                )

            # Base filename taken - convert to indexed MacroPath and scan
            macro_path = self._convert_str_path_to_macro_with_index(request.file_path)
        else:
            # MacroPath provided directly
            macro_path = request.file_path

        parsed_macro = macro_path.parsed_macro
        variables = macro_path.variables

        # Identify index variable
        try:
            index_info = self._identify_index_variable(parsed_macro, variables)
        except ValueError as e:
            msg = str(e)
            logger.error(msg)
            return GetNextUnusedFilenameResultFailure(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details=msg,
            )

        if index_info is None:
            # No unresolved variables - cannot auto-increment
            msg = "No index variable found in path template"
            logger.error(msg)
            return GetNextUnusedFilenameResultFailure(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details=msg,
            )

        # Scan for next available index (preview only - no file creation)
        next_index = self._scan_for_next_available_index(parsed_macro, variables, index_info)

        # Resolve path with the index
        secrets_manager = GriptapeNodes.SecretsManager()
        try:
            if next_index is None:
                # Optional index variable with base filename available
                available_filename = parsed_macro.resolve(variables, secrets_manager)
            else:
                # Use indexed filename
                index_vars = {**variables, index_info.info.name: next_index}
                available_filename = parsed_macro.resolve(index_vars, secrets_manager)
        except MacroResolutionError as e:
            msg = f"Failed to resolve path template: {e}"
            logger.error(msg)
            return GetNextUnusedFilenameResultFailure(
                failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
                result_details=msg,
            )

        return GetNextUnusedFilenameResultSuccess(
            available_filename=available_filename,
            index_used=next_index,
            result_details=f"Found available filename with index {next_index}"
            if next_index
            else "Found available filename (no index needed)",
        )

    def on_write_file_request(self, request: WriteFileRequest) -> ResultPayload:  # noqa: PLR0911, PLR0912, PLR0915, C901
        """Handle a request to write content to a file with exclusive locking."""
        # Initialize success tracking variables
        final_file_path: Path | None = None
        final_bytes_written: int | None = None
        used_indexed_fallback = False

        # COMMON SETUP: Resolve path for all policies
        # Resolve MacroPath → str
        if isinstance(request.file_path, MacroPath):
            resolution_result = self._resolve_macro_path_to_string(request.file_path)
            if isinstance(resolution_result, MacroResolutionFailure):
                path_display = f"{request.file_path.parsed_macro}"
                msg = f"Attempted to write to file '{path_display}'. Failed due to missing variables: {resolution_result.error_details}"
                return WriteFileResultFailure(
                    failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
                    missing_variables=resolution_result.missing_variables,
                    result_details=msg,
                )
            resolved_path_str = resolution_result
            path_display = f"{request.file_path.parsed_macro}"
        else:
            # Sanitize string path (removes shell escapes, quotes, etc.)
            resolved_path_str = self.sanitize_path_string(request.file_path)
            path_display = resolved_path_str

        # Convert str → Path
        try:
            file_path = self._resolve_file_path(resolved_path_str, workspace_only=False)
        except (ValueError, RuntimeError) as e:
            msg = f"Attempted to write to file '{path_display}'. Failed due to invalid path: {e}"
            return WriteFileResultFailure(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details=msg,
            )
        except Exception as e:
            msg = f"Attempted to write to file '{path_display}'. Failed due to unexpected error: {e}"
            return WriteFileResultFailure(
                failure_reason=FileIOFailureReason.IO_ERROR,
                result_details=msg,
            )

        # Ensure parent directory is ready
        parent_failure_reason = self._ensure_parent_directory_ready(
            file_path,
            create_parents=request.create_parents,
        )
        if parent_failure_reason is not None:
            match parent_failure_reason:
                case FileIOFailureReason.PERMISSION_DENIED:
                    msg = f"Attempted to write to file '{file_path}'. Failed due to permission denied creating parent directory {file_path.parent}"
                case FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS:
                    msg = f"Attempted to write to file '{file_path}'. Failed due to the parent directory not existing, and a policy was specified to NOT create parent directories: {file_path.parent}"
                case _:
                    msg = f"Attempted to write to file '{file_path}'. Failed due to error creating parent directory {file_path.parent}"
            return WriteFileResultFailure(
                failure_reason=parent_failure_reason,
                result_details=msg,
            )

        # Normalize path
        normalized_path = self.normalize_path_for_platform(file_path)

        # Now attempt the write, based on our collision (existing file) policy.
        match request.existing_file_policy:
            case ExistingFilePolicy.FAIL | ExistingFilePolicy.OVERWRITE:
                # Path already validated and ready to use

                # Determine write mode based on policy
                if request.existing_file_policy == ExistingFilePolicy.FAIL:
                    mode = "x"  # Exclusive creation (fail if exists)
                else:
                    mode = "a" if request.append else "w"  # Append or overwrite

                # Perform the write operation using helper
                result = self._attempt_file_write(
                    normalized_path=Path(normalized_path),
                    content=request.content,
                    encoding=request.encoding,
                    mode=mode,
                    file_path_display=file_path,
                    fail_if_file_exists=True,  # FAIL policy always fails on file exists
                    fail_if_file_locked=True,
                )
                if result.failure_reason is not None:
                    # error_message is guaranteed to be set when failure_reason is set
                    return WriteFileResultFailure(
                        failure_reason=result.failure_reason,
                        result_details=result.error_message,  # type: ignore[arg-type]
                    )

                # Success - set variables for return at end
                final_file_path = file_path
                final_bytes_written = result.bytes_written

            case ExistingFilePolicy.CREATE_NEW:
                # Path already validated and ready to use (handled at method top)

                # TRY-FIRST: Attempt to write to the requested path
                result = self._attempt_file_write(
                    normalized_path=Path(normalized_path),
                    content=request.content,
                    encoding=request.encoding,
                    mode="x",
                    file_path_display=file_path,
                    fail_if_file_exists=False,  # Fall back to indexed
                    fail_if_file_locked=False,  # Fall back to indexed
                )
                if result.failure_reason is not None:
                    # error_message is guaranteed to be set when failure_reason is set
                    return WriteFileResultFailure(
                        failure_reason=result.failure_reason,
                        result_details=result.error_message,  # type: ignore[arg-type]
                    )
                if result.bytes_written is not None:
                    # Success on first try!
                    final_file_path = file_path
                    final_bytes_written = result.bytes_written
                else:
                    # FILE EXISTS OR IS LOCKED. ATTEMPT TO FIND THE NEXT AVAILABLE.
                    # Convert to indexed MacroPath for scanning. If the user didn't give us a macro to start with,
                    # we'll take their file name and turn it into a macro that appends _<index> to it.
                    # (e.g., if they gave us "output.png" we'll convert that to a macro that tries "output_1.png", "output_2.png", etc.)
                    macro_path = (
                        self._convert_str_path_to_macro_with_index(request.file_path)
                        if isinstance(request.file_path, str)
                        else request.file_path
                    )
                    parsed_macro = macro_path.parsed_macro
                    variables = macro_path.variables

                    # Identify index variable
                    try:
                        index_info = self._identify_index_variable(parsed_macro, variables)
                    except ValueError as e:
                        msg = f"Attempted to write to file '{path_display}'. Failed due to {e}"
                        return WriteFileResultFailure(
                            failure_reason=FileIOFailureReason.INVALID_PATH,
                            result_details=msg,
                        )
                    except Exception as e:
                        msg = f"Attempted to write to file '{path_display}'. Failed due to unexpected error: {e}"
                        return WriteFileResultFailure(
                            failure_reason=FileIOFailureReason.IO_ERROR,
                            result_details=msg,
                        )

                    if index_info is None:
                        msg = f"Attempted to write to file '{path_display}'. Failed due to no index variable found in path template"
                        return WriteFileResultFailure(
                            failure_reason=FileIOFailureReason.INVALID_PATH,
                            result_details=msg,
                        )

                    # We have a macro with one and only one index variable on it. The heuristic here is:
                    # 1. Find the FIRST available file name with our index. We'll start there, but someone else may have
                    #    ganked it while we were attempting to write to it.
                    # 2. Try candidates in sequence until we find one that works, or fail if we've tried too many times.
                    # Note: The user could have specified using the index value as a DIRECTORY,
                    # so it's not always output_1, output_2, etc. It could be run_1/output.png, run_2/output.png, etc.

                    # Scan for starting index
                    starting_index = self._scan_for_next_available_index(parsed_macro, variables, index_info)

                    # Try indexed candidates on-demand (up to max attempts)
                    secrets_manager = GriptapeNodes.SecretsManager()
                    start_idx = starting_index if starting_index is not None else 1
                    attempted_count = 0

                    for idx in range(start_idx, start_idx + MAX_INDEXED_CANDIDATES):
                        attempted_count += 1

                        # Step 1: Resolve macro with current index
                        try:
                            index_vars = {**variables, index_info.info.name: idx}
                            candidate_str = parsed_macro.resolve(index_vars, secrets_manager)
                        except MacroResolutionError as e:
                            msg = f"Attempted to write to file '{path_display}'. Failed due to unable to resolve path template with index {idx}: {e}"
                            return WriteFileResultFailure(
                                failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
                                result_details=msg,
                            )
                        except Exception as e:
                            msg = f"Attempted to write to file '{path_display}'. Failed due to unexpected error: {e}"
                            return WriteFileResultFailure(
                                failure_reason=FileIOFailureReason.IO_ERROR,
                                result_details=msg,
                            )

                        # Step 2: Resolve file path
                        try:
                            candidate_path = self._resolve_file_path(candidate_str, workspace_only=False)
                        except (ValueError, RuntimeError) as e:
                            msg = f"Attempted to write to file '{candidate_str}'. Failed due to invalid path: {e}"
                            return WriteFileResultFailure(
                                failure_reason=FileIOFailureReason.INVALID_PATH,
                                result_details=msg,
                            )
                        except Exception as e:
                            msg = f"Attempted to write to file '{candidate_str}'. Failed due to unexpected error: {e}"
                            return WriteFileResultFailure(
                                failure_reason=FileIOFailureReason.IO_ERROR,
                                result_details=msg,
                            )

                        # Ensure parent directory for this candidate
                        parent_failure_reason = self._ensure_parent_directory_ready(
                            candidate_path,
                            create_parents=request.create_parents,
                        )
                        if parent_failure_reason is not None:
                            match parent_failure_reason:
                                case FileIOFailureReason.PERMISSION_DENIED:
                                    msg = f"Attempted to write to file '{candidate_path}'. Failed due to permission denied creating parent directory {candidate_path.parent}"
                                case FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS:
                                    msg = f"Attempted to write to file '{candidate_path}'. Failed due to the parent directory not existing, and a policy was specified to NOT create parent directories: {candidate_path.parent}"
                                case _:
                                    msg = f"Attempted to write to file '{candidate_path}'. Failed due to error creating parent directory {candidate_path.parent}"
                            return WriteFileResultFailure(
                                failure_reason=parent_failure_reason,
                                result_details=msg,
                            )

                        normalized_candidate_path = self.normalize_path_for_platform(candidate_path)

                        # Try to write this indexed candidate using helper
                        result = self._attempt_file_write(
                            normalized_path=Path(normalized_candidate_path),
                            content=request.content,
                            encoding=request.encoding,
                            mode="x",
                            file_path_display=candidate_path,
                            fail_if_file_exists=False,  # Try next candidate
                            fail_if_file_locked=False,  # Try next candidate
                        )
                        if result.failure_reason is not None:
                            # error_message is guaranteed to be set when failure_reason is set
                            return WriteFileResultFailure(
                                failure_reason=result.failure_reason,
                                result_details=result.error_message,  # type: ignore[arg-type]
                            )
                        if result.bytes_written is not None:
                            # Success with indexed path!
                            final_file_path = candidate_path
                            final_bytes_written = result.bytes_written
                            used_indexed_fallback = True
                            break
                        # else: continue to next candidate

                    # Check if we exhausted all indexed candidates
                    if final_file_path is None:
                        msg = f"Attempted to write to file '{path_display}'. Failed due to could not find available filename after trying {attempted_count} candidates"
                        return WriteFileResultFailure(
                            failure_reason=FileIOFailureReason.IO_ERROR,
                            result_details=msg,
                        )

        # SUCCESS PATH: All three policies converge here
        if final_file_path is None or final_bytes_written is None:
            msg = "Internal error: success path reached but file path or bytes not set"
            raise RuntimeError(msg)

        if used_indexed_fallback:
            msg = f"File written to indexed path: {final_file_path} (original path '{path_display}' already existed)"
            result_details = ResultDetails(message=msg, level=logging.WARNING)
        else:
            result_details = f"File written successfully: {final_file_path}"

        return WriteFileResultSuccess(
            final_file_path=str(final_file_path),
            bytes_written=final_bytes_written,
            result_details=result_details,
        )

    def _ensure_parent_directory_ready(
        self,
        file_path: Path,
        *,
        create_parents: bool,
    ) -> FileIOFailureReason | None:
        """Ensure parent directory exists or create it.

        Args:
            file_path: The file path whose parent should be validated/created
            create_parents: If True, create parent dirs; if False, validate they exist

        Returns:
            None on success, FileIOFailureReason if validation/creation fails
        """
        if create_parents:
            parent_normalized = self.normalize_path_for_platform(file_path.parent)
            try:
                if not Path(parent_normalized).exists():
                    Path(parent_normalized).mkdir(parents=True, exist_ok=True)
            except PermissionError:
                return FileIOFailureReason.PERMISSION_DENIED
            except OSError:
                return FileIOFailureReason.IO_ERROR
        elif not file_path.parent.exists():
            return FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS

        return None

    def _attempt_file_write(  # noqa: PLR0911, PLR0913
        self,
        normalized_path: Path,
        content: str | bytes,
        encoding: str,
        mode: str,
        file_path_display: str | Path,
        *,
        fail_if_file_exists: bool,
        fail_if_file_locked: bool,
    ) -> FileWriteAttemptResult:
        """Attempt to write a file with unified exception handling.

        Args:
            normalized_path: The normalized path to write to
            content: Content to write (str or bytes)
            encoding: Encoding for text content
            mode: Write mode ("x", "w", "a")
            file_path_display: Path to use in error messages
            fail_if_file_exists: If True, return failure when file exists; if False, return continue signal
            fail_if_file_locked: If True, return failure when file is locked; if False, return continue signal

        Returns:
            FileWriteAttemptResult with one of:
            - Success: bytes_written is set, failure_reason and error_message are None
            - Continue: all fields are None (file exists/locked but caller wants to continue)
            - Failure: failure_reason and error_message are set, bytes_written is None
        """
        try:
            bytes_written = self._write_with_portalocker(
                str(normalized_path),
                content,
                encoding,
                mode=mode,
            )
            # Success!
            return FileWriteAttemptResult(
                bytes_written=bytes_written,
                failure_reason=None,
                error_message=None,
            )
        except FileExistsError:
            if fail_if_file_exists:
                msg = f"Attempted to write to file '{file_path_display}'. Failed due to file already exists (policy: fail if exists)"
                return FileWriteAttemptResult(
                    bytes_written=None,
                    failure_reason=FileIOFailureReason.POLICY_NO_OVERWRITE,
                    error_message=msg,
                )
            # Continue signal - caller should try next candidate or fallback
            return FileWriteAttemptResult(
                bytes_written=None,
                failure_reason=None,
                error_message=None,
            )
        except portalocker.LockException:
            if fail_if_file_locked:
                msg = f"Attempted to write to file '{file_path_display}'. Failed due to file locked by another process"
                return FileWriteAttemptResult(
                    bytes_written=None,
                    failure_reason=FileIOFailureReason.FILE_LOCKED,
                    error_message=msg,
                )
            # Continue signal - caller should try next candidate or fallback
            return FileWriteAttemptResult(
                bytes_written=None,
                failure_reason=None,
                error_message=None,
            )
        except PermissionError as e:
            msg = f"Attempted to write to file '{file_path_display}'. Failed due to permission denied: {e}"
            return FileWriteAttemptResult(
                bytes_written=None,
                failure_reason=FileIOFailureReason.PERMISSION_DENIED,
                error_message=msg,
            )
        except IsADirectoryError as e:
            msg = f"Attempted to write to file '{file_path_display}'. Failed due to path is a directory: {e}"
            return FileWriteAttemptResult(
                bytes_written=None,
                failure_reason=FileIOFailureReason.IS_DIRECTORY,
                error_message=msg,
            )
        except Exception as e:
            msg = f"Attempted to write to file '{file_path_display}'. Failed due to unexpected error: {e}"
            return FileWriteAttemptResult(
                bytes_written=None,
                failure_reason=FileIOFailureReason.IO_ERROR,
                error_message=msg,
            )

    def _write_with_portalocker(  # noqa: C901
        self, normalized_path: str, content: str | bytes, encoding: str, *, mode: str
    ) -> int:
        """Write content to a file with exclusive lock using portalocker.

        Args:
            normalized_path: Normalized path string (with Windows long path prefix if needed)
            content: Content to write (str for text, bytes for binary)
            encoding: Text encoding (ignored for bytes)
            mode: File open mode ('x' for exclusive create, 'w' for overwrite, 'a' for append)

        Returns:
            Number of bytes written

        Raises:
            FileExistsError: If mode='x' and file already exists
            portalocker.LockException: If file is locked by another process
            PermissionError: If permission denied
            IsADirectoryError: If path is a directory
            UnicodeEncodeError: If encoding error occurs
            OSError: For other I/O errors
        """
        error_details = None

        try:
            # Determine binary vs text mode
            if isinstance(content, bytes):
                file_mode = mode + "b"
            else:
                file_mode = mode

            with portalocker.Lock(
                normalized_path,
                mode=file_mode,  # type: ignore[arg-type]
                encoding=encoding if isinstance(content, str) else None,
                timeout=0,  # Non-blocking
                flags=portalocker.LockFlags.EXCLUSIVE,
            ) as fh:
                fh.write(content)

            # Calculate bytes written
            if isinstance(content, bytes):
                return len(content)
            return len(content.encode(encoding))

        except portalocker.LockException:
            raise
        except FileExistsError:
            raise
        except PermissionError:
            raise
        except IsADirectoryError:
            raise
        except UnicodeEncodeError:
            raise
        except OSError as e:
            # Check for disk full
            if "No space left" in str(e) or "Disk full" in str(e):
                error_details = f"Disk full: {e}"
                logger.error(error_details)
                raise OSError(error_details) from e
            raise
        except Exception as e:
            error_details = f"Unexpected error: {type(e).__name__}: {e}"
            logger.error(error_details)
            raise

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
        return Path(src_normalized).stat().st_size

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

    # Resource Management Methods
    def _register_system_resources_direct(self) -> None:
        """Register OS, CPU, and Compute resource types directly during initialization.

        This method is called during __init__ and uses the event_manager directly
        to avoid singleton recursion issues with GriptapeNodes.handle_request.
        """
        self._attempt_generate_os_resources_direct()
        self._attempt_generate_cpu_resources_direct()
        self._attempt_generate_compute_resources_direct()

    def _handle_request_direct(self, request: Any) -> Any:
        """Handle a request directly through the event_manager during initialization.

        This bypasses GriptapeNodes.handle_request to avoid singleton recursion.
        """
        request_type = type(request)
        callback = self._event_manager._request_type_to_manager.get(request_type)
        if not callback:
            msg = f"No manager found to handle request of type '{request_type.__name__}'."
            raise TypeError(msg)
        return callback(request)

    def _register_system_resources(self) -> None:
        """Register OS, CPU, and Compute resource types with ResourceManager and create system instances."""
        self._attempt_generate_os_resources()
        self._attempt_generate_cpu_resources()
        self._attempt_generate_compute_resources()

    def _attempt_generate_os_resources_direct(self) -> None:
        """Register OS resource type and create system OS instance (direct version for init)."""
        os_resource_type = OSResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=os_resource_type)
        result = self._handle_request_direct(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error("Attempted to register OS resource type. Failed due to resource type registration failure")
            return

        logger.debug("Successfully registered OS resource type")
        self._create_system_os_instance_direct()

    def _attempt_generate_cpu_resources_direct(self) -> None:
        """Register CPU resource type and create system CPU instance (direct version for init)."""
        cpu_resource_type = CPUResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=cpu_resource_type)
        result = self._handle_request_direct(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error("Attempted to register CPU resource type. Failed due to resource type registration failure")
            return

        logger.debug("Successfully registered CPU resource type")
        self._create_system_cpu_instance_direct()

    def _attempt_generate_compute_resources_direct(self) -> None:
        """Register Compute resource type and create system compute instance (direct version for init)."""
        compute_resource_type = ComputeResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=compute_resource_type)
        result = self._handle_request_direct(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error(
                "Attempted to register Compute resource type. Failed due to resource type registration failure"
            )
            return

        logger.debug("Successfully registered Compute resource type")
        self._create_system_compute_instance_direct()

    def _create_system_os_instance_direct(self) -> None:
        """Create system OS instance (direct version for init)."""
        os_capabilities = {
            "platform": self._get_platform_name(),
            "arch": self._get_architecture(),
            "version": self._get_platform_version(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="OSResourceType", capabilities=os_capabilities
        )
        result = self._handle_request_direct(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system OS resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system OS instance: %s", result.instance_id)

    def _create_system_cpu_instance_direct(self) -> None:
        """Create system CPU instance (direct version for init)."""
        cpu_capabilities = {
            "cores": os.cpu_count() or 1,
            "architecture": self._get_architecture(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="CPUResourceType", capabilities=cpu_capabilities
        )
        result = self._handle_request_direct(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system CPU resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system CPU instance: %s", result.instance_id)

    def _create_system_compute_instance_direct(self) -> None:
        """Create system compute instance with detected backends (direct version for init)."""
        compute_capabilities = {
            "compute": self._get_available_compute_backends(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="ComputeResourceType", capabilities=compute_capabilities
        )
        result = self._handle_request_direct(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system Compute resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system Compute instance: %s", result.instance_id)

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

    def _attempt_generate_compute_resources(self) -> None:
        """Register Compute resource type and create system compute instance if successful."""
        # Register Compute resource type
        compute_resource_type = ComputeResourceType()
        register_request = RegisterResourceTypeRequest(resource_type=compute_resource_type)
        result = GriptapeNodes.handle_request(register_request)

        if not isinstance(result, RegisterResourceTypeResultSuccess):
            logger.error(
                "Attempted to register Compute resource type. Failed due to resource type registration failure"
            )
            return

        logger.debug("Successfully registered Compute resource type")
        # Registration successful, now create instance
        self._create_system_compute_instance()

    def _create_system_compute_instance(self) -> None:
        """Create system compute instance with detected backends."""
        compute_capabilities = {
            "compute": self._get_available_compute_backends(),
        }
        create_request = CreateResourceInstanceRequest(
            resource_type_name="ComputeResourceType", capabilities=compute_capabilities
        )
        result = GriptapeNodes.handle_request(create_request)

        if not isinstance(result, CreateResourceInstanceResultSuccess):
            logger.error(
                "Attempted to create system Compute resource instance. Failed due to resource instance creation failure"
            )
            return

        logger.debug("Successfully created system Compute instance: %s", result.instance_id)

    def _get_available_compute_backends(self) -> list[str]:
        """Detect available compute backends on the system.

        Returns:
            List of available backends: always includes 'cpu', plus 'cuda' or 'mps' if available.
        """
        backends: list[str] = [ComputeBackend.CPU]  # CPU is always available

        # Check for CUDA (NVIDIA GPU)
        if self._is_cuda_available():
            backends.append(ComputeBackend.CUDA)

        # Check for MPS (Apple Silicon)
        if self._is_mps_available():
            backends.append(ComputeBackend.MPS)

        logger.debug("Detected compute backends: %s", backends)
        return backends

    def _is_cuda_available(self) -> bool:
        """Check if CUDA is available by detecting NVIDIA driver.

        Uses nvidia-smi command which is lightweight and doesn't require torch.
        """
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi is None:
            return False
        try:
            result = subprocess.run(  # noqa: S603
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("CUDA detected via nvidia-smi: %s", result.stdout.strip().split("\n")[0])
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
        return False

    def _is_mps_available(self) -> bool:
        """Check if MPS (Metal Performance Shaders) is available.

        MPS is available on Apple Silicon Macs (arm64 architecture) with macOS 12.3+.
        """
        if not self.is_mac():
            return False

        # Check for Apple Silicon (arm64)
        arch = self._get_architecture()
        if arch not in (Architecture.ARM64, Architecture.AARCH64):
            return False

        # MPS requires macOS 12.3+, but arm64 Macs shipped with 11.0+
        # and all arm64 Macs can run 12.3+, so if it's arm64 Mac, MPS is available
        logger.debug("MPS detected: Apple Silicon Mac")
        return True

    def _get_platform_name(self) -> str:
        """Get platform name using existing sys.platform detection."""
        if self.is_windows():
            return Platform.WINDOWS
        if self.is_mac():
            return Platform.DARWIN
        if self.is_linux():
            return Platform.LINUX
        return sys.platform

    def _get_architecture(self) -> str:
        """Get system architecture, normalized across platforms."""
        platform = self._get_platform_name()
        if platform == Platform.WINDOWS:
            arch = os.environ.get("PROCESSOR_ARCHITECTURE", "unknown").lower()
        else:
            arch = os.uname().machine.lower()

        # Normalize architecture names across platforms
        # Windows reports "amd64", Linux/macOS report "x86_64" - they're the same
        if arch == "amd64":
            return Architecture.X86_64
        if arch == "x86_64":
            return Architecture.X86_64
        if arch == "arm64":
            return Architecture.ARM64
        if arch == "aarch64":
            return Architecture.AARCH64
        return arch

    def _get_platform_version(self) -> str:
        """Get platform version."""
        try:
            return os.uname().release
        except AttributeError:
            # Windows doesn't have os.uname(), return basic platform info
            return sys.platform
