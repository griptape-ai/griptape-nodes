from dataclasses import dataclass
from enum import StrEnum

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


class ExistingFilePolicy(StrEnum):
    """Policy for handling existing files during write operations."""

    OVERWRITE = "overwrite"  # Replace existing file content
    FAIL = "fail"  # Fail if file exists
    CREATE_NEW = "create_new"  # Create new file with modified name (e.g., file_1.txt)


class FileIOFailureReason(StrEnum):
    """Classification of file I/O failure reasons.

    Used by read and write operations to provide structured error information.
    """

    # Policy violations
    POLICY_NO_OVERWRITE = "policy_no_overwrite"  # File exists and policy prohibits overwrite
    POLICY_NO_CREATE_PARENT_DIRS = "policy_no_create_parent_dirs"  # Parent dir missing and policy prohibits creation

    # Permission/access errors
    PERMISSION_DENIED = "permission_denied"  # No read/write permission
    FILE_NOT_FOUND = "file_not_found"  # File doesn't exist (read operations)

    # Resource errors
    DISK_FULL = "disk_full"  # Insufficient disk space

    # Path errors
    INVALID_PATH = "invalid_path"  # Malformed or invalid path
    IS_DIRECTORY = "is_directory"  # Path is a directory, not a file

    # Content errors
    ENCODING_ERROR = "encoding_error"  # Text encoding/decoding failed

    # Generic errors
    IO_ERROR = "io_error"  # Generic I/O error
    UNKNOWN = "unknown"  # Unexpected error


@dataclass
class FileSystemEntry:
    """Represents a file or directory in the file system."""

    name: str
    path: str  # Workspace-relative path (for portability)
    is_dir: bool
    size: int
    modified_time: float
    absolute_path: str  # Absolute resolved path
    mime_type: str | None = None  # None for directories, mimetype for files


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileRequest(RequestPayload):
    """Open a file or directory using the operating system's associated application.

    Use when: Opening generated files, launching external applications,
    providing file viewing capabilities, implementing file associations,
    opening folders in system explorer.

    Args:
        path_to_file: Path to the file or directory to open (mutually exclusive with file_entry)
        file_entry: FileSystemEntry object from directory listing (mutually exclusive with path_to_file)

    Results: OpenAssociatedFileResultSuccess | OpenAssociatedFileResultFailure (path not found, no association)
    """

    path_to_file: str | None = None
    file_entry: FileSystemEntry | None = None


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File or directory opened successfully with associated application."""


@dataclass
@PayloadRegistry.register
class OpenAssociatedFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File or directory opening failed.

    Attributes:
        failure_reason: Classification of why the open failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class ListDirectoryRequest(RequestPayload):
    """List contents of a directory.

    Use when: Browsing file system, showing directory contents,
    implementing file pickers, navigating folder structures.

    Args:
        directory_path: Path to the directory to list (None for current directory)
        show_hidden: Whether to show hidden files/folders
        workspace_only: If True, constrain to workspace directory. If False, allow system-wide browsing.
                        If None, workspace constraints don't apply (e.g., cloud environments).
        pattern: Optional glob pattern to filter entries (e.g., "*.txt", "file_*.json").
                 Only matches against file/directory names, not full paths.

    Results: ListDirectoryResultSuccess (with entries) | ListDirectoryResultFailure (access denied, not found)
    """

    directory_path: str | None = None
    show_hidden: bool = False
    workspace_only: bool | None = True
    pattern: str | None = None


@dataclass
@PayloadRegistry.register
class ListDirectoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Directory listing retrieved successfully."""

    entries: list[FileSystemEntry]
    current_path: str
    is_workspace_path: bool


@dataclass
@PayloadRegistry.register
class ListDirectoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Directory listing failed.

    Attributes:
        failure_reason: Classification of why the listing failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class ReadFileRequest(RequestPayload):
    """Read contents of a file, automatically detecting if it's text or binary using MIME types.

    Use when: Reading file contents for display, processing, or analysis.
    Automatically detects file type using MIME type detection and returns appropriate content format.

    Args:
        file_path: Path to the file to read (mutually exclusive with file_entry)
        file_entry: FileSystemEntry object from directory listing (mutually exclusive with file_path)
        encoding: Text encoding to use if file is detected as text (default: 'utf-8')
        workspace_only: If True, constrain to workspace directory. If False, allow system-wide access.
                        If None, workspace constraints don't apply (e.g., cloud environments).
                        TODO: Remove workspace_only parameter - see https://github.com/griptape-ai/griptape-nodes/issues/2753

    Results: ReadFileResultSuccess (with content) | ReadFileResultFailure (file not found, permission denied)
    """

    file_path: str | None = None
    file_entry: FileSystemEntry | None = None
    encoding: str = "utf-8"
    workspace_only: bool | None = True  # TODO: Remove - see https://github.com/griptape-ai/griptape-nodes/issues/2753


@dataclass
@PayloadRegistry.register
class ReadFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File contents read successfully."""

    content: str | bytes  # String for text files, bytes for binary files
    file_size: int
    mime_type: str  # e.g., "text/plain", "image/png", "application/pdf"
    encoding: str | None  # Text encoding used (None for binary files)
    compression_encoding: str | None = None  # Compression encoding (e.g., "gzip", "bzip2", None)
    is_text: bool = False  # Will be computed from content type

    def __post_init__(self) -> None:
        """Compute is_text from content type after initialization."""
        # For images, even though content is a string (base64), it's not text content
        if self.mime_type.startswith("image/"):
            self.is_text = False
        else:
            self.is_text = isinstance(self.content, str)


@dataclass
@PayloadRegistry.register
class ReadFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File reading failed.

    Attributes:
        failure_reason: Classification of why the read failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class CreateFileRequest(RequestPayload):
    """Create a new file or directory.

    Use when: Creating files/directories through file picker,
    implementing file creation functionality.

    Args:
        path: Path where the file/directory should be created (legacy, use directory_path + name instead)
        directory_path: Directory where to create the file/directory (mutually exclusive with path)
        name: Name of the file/directory to create (mutually exclusive with path)
        is_directory: True to create a directory, False for a file
        content: Initial content for files (optional)
        encoding: Text encoding for file content (default: 'utf-8')
        workspace_only: If True, constrain to workspace directory

    Results: CreateFileResultSuccess | CreateFileResultFailure
    """

    path: str | None = None
    directory_path: str | None = None
    name: str | None = None
    is_directory: bool = False
    content: str | None = None
    encoding: str = "utf-8"
    workspace_only: bool | None = True

    def get_full_path(self) -> str:
        """Get the full path, constructing from directory_path + name if path is not provided."""
        if self.path is not None:
            return self.path
        if self.directory_path is not None and self.name is not None:
            from pathlib import Path

            return str(Path(self.directory_path) / self.name)
        msg = "Either 'path' or both 'directory_path' and 'name' must be provided"
        raise ValueError(msg)


@dataclass
@PayloadRegistry.register
class CreateFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File/directory created successfully."""

    created_path: str


@dataclass
@PayloadRegistry.register
class CreateFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File/directory creation failed.

    Attributes:
        failure_reason: Classification of why the creation failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class RenameFileRequest(RequestPayload):
    """Rename a file or directory.

    Use when: Renaming files/directories through file picker,
    implementing file rename functionality.

    Args:
        old_path: Current path of the file/directory to rename
        new_path: New path for the file/directory
        workspace_only: If True, constrain to workspace directory

    Results: RenameFileResultSuccess | RenameFileResultFailure
    """

    old_path: str
    new_path: str
    workspace_only: bool | None = True


@dataclass
@PayloadRegistry.register
class RenameFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File/directory renamed successfully."""

    old_path: str
    new_path: str


@dataclass
@PayloadRegistry.register
class RenameFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File/directory rename failed.

    Attributes:
        failure_reason: Classification of why the rename failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class WriteFileRequest(RequestPayload):
    """Write content to a file.

    Automatically detects text vs binary mode based on content type.

    Use when: Saving generated content, writing output files,
    creating configuration files, writing binary data.

    Args:
        file_path: Path to the file to write
        content: Content to write (str for text files, bytes for binary files)
        encoding: Text encoding for str content (default: 'utf-8', ignored for bytes)
        append: If True, append to existing file; if False, use existing_file_policy (default: False)
        existing_file_policy: How to handle existing files when append=False:
            - "overwrite": Replace file content (default)
            - "fail": Return failure if file exists
            - "create_new": Create new file with modified name (NOT YET IMPLEMENTED)
        create_parents: If True, create parent directories if missing (default: True)

    Results: WriteFileResultSuccess | WriteFileResultFailure

    Note: existing_file_policy is ignored when append=True (append always allows existing files)
    """

    file_path: str
    content: str | bytes
    encoding: str = "utf-8"  # Ignored for bytes
    append: bool = False
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    create_parents: bool = True


@dataclass
@PayloadRegistry.register
class WriteFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File written successfully.

    Attributes:
        final_file_path: The actual path where file was written
                        (may differ from requested path if create_new policy used)
        bytes_written: Number of bytes written to the file
    """

    final_file_path: str
    bytes_written: int


@dataclass
@PayloadRegistry.register
class WriteFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File write failed.

    Attributes:
        failure_reason: Classification of why the write failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class CopyTreeRequest(RequestPayload):
    """Copy an entire directory tree from source to destination.

    Use when: Copying directories recursively, backing up directory structures,
    duplicating folder hierarchies with all contents.

    Args:
        source_path: Path to the source directory to copy
        destination_path: Path where the directory tree should be copied
        symlinks: If True, copy symbolic links as links (default: False)
        ignore_dangling_symlinks: If True, ignore dangling symlinks (default: False)
        dirs_exist_ok: If True, allow destination to exist (default: False)
        ignore_patterns: List of glob patterns to ignore (e.g., ["__pycache__", "*.pyc", ".git"])

    Results: CopyTreeResultSuccess | CopyTreeResultFailure
    """

    source_path: str
    destination_path: str
    symlinks: bool = False
    ignore_dangling_symlinks: bool = False
    dirs_exist_ok: bool = False
    ignore_patterns: list[str] | None = None


@dataclass
@PayloadRegistry.register
class CopyTreeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Directory tree copied successfully.

    Attributes:
        source_path: Source path that was copied
        destination_path: Destination path where tree was copied
        files_copied: Number of files copied
        total_bytes_copied: Total bytes copied
    """

    source_path: str
    destination_path: str
    files_copied: int
    total_bytes_copied: int


@dataclass
@PayloadRegistry.register
class CopyTreeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Directory tree copy failed.

    Attributes:
        failure_reason: Classification of why the copy failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class CopyFileRequest(RequestPayload):
    """Copy a single file from source to destination.

    Use when: Copying individual files, duplicating files,
    backing up single files.

    Args:
        source_path: Path to the source file to copy
        destination_path: Path where the file should be copied
        overwrite: If True, overwrite destination if it exists (default: False)

    Results: CopyFileResultSuccess | CopyFileResultFailure
    """

    source_path: str
    destination_path: str
    overwrite: bool = False


@dataclass
@PayloadRegistry.register
class CopyFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File copied successfully.

    Attributes:
        source_path: Source path that was copied
        destination_path: Destination path where file was copied
        bytes_copied: Number of bytes copied
    """

    source_path: str
    destination_path: str
    bytes_copied: int


@dataclass
@PayloadRegistry.register
class CopyFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File copy failed.

    Attributes:
        failure_reason: Classification of why the copy failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class DeleteFileRequest(RequestPayload):
    """Delete a file or directory.

    Use when: Deleting files/directories through file picker,
    implementing file deletion functionality, cleaning up temporary files.

    Note: Directories are always deleted with all their contents.

    Args:
        path: Path to file/directory to delete (mutually exclusive with file_entry)
        file_entry: FileSystemEntry from directory listing (mutually exclusive with path)
        workspace_only: If True, constrain to workspace directory

    Results: DeleteFileResultSuccess | DeleteFileResultFailure
    """

    path: str | None = None
    file_entry: FileSystemEntry | None = None
    workspace_only: bool | None = True


@dataclass
@PayloadRegistry.register
class DeleteFileResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File/directory deleted successfully.

    Attributes:
        deleted_path: The absolute path that was deleted (primary path)
        was_directory: Whether the deleted item was a directory
        deleted_paths: List of all paths that were deleted (for recursive deletes, includes all files/dirs)
    """

    deleted_path: str
    was_directory: bool
    deleted_paths: list[str]


@dataclass
@PayloadRegistry.register
class DeleteFileResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File/directory deletion failed.

    Attributes:
        failure_reason: Classification of why the deletion failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason


@dataclass
@PayloadRegistry.register
class GetFileInfoRequest(RequestPayload):
    """Get information about a file or directory.

    Use when: Checking if a path exists, determining if path is file/directory,
    getting file metadata before operations.

    Args:
        path: Path to file/directory to get info about
        workspace_only: If True, constrain to workspace directory

    Results: GetFileInfoResultSuccess | GetFileInfoResultFailure
    """

    path: str
    workspace_only: bool | None = True


@dataclass
@PayloadRegistry.register
class GetFileInfoResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """File/directory either did not exist (we do not treat this as failure), or the info was retrieved successfully.

    Attributes:
        file_entry: FileSystemEntry with complete metadata, or None if the file/directory doesn't exist
    """

    file_entry: FileSystemEntry | None


@dataclass
@PayloadRegistry.register
class GetFileInfoResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """File/directory info retrieval failed.

    Attributes:
        failure_reason: Classification of why retrieval failed
        result_details: Human-readable error message (inherited from ResultPayloadFailure)
    """

    failure_reason: FileIOFailureReason
