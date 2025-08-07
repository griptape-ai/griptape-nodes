from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
class FileSystemEntry:
    """Represents a file or directory in the file system."""

    name: str
    path: str
    is_dir: bool
    size: int
    modified_time: float
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
    """File or directory opening failed. Common causes: path not found, no associated application, permission denied."""


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

    Results: ListDirectoryResultSuccess (with entries) | ListDirectoryResultFailure (access denied, not found)
    """

    directory_path: str | None = None
    show_hidden: bool = False
    workspace_only: bool | None = True


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
    """Directory listing failed. Common causes: access denied, path not found."""


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

    Results: ReadFileResultSuccess (with content) | ReadFileResultFailure (file not found, permission denied)
    """

    file_path: str | None = None
    file_entry: FileSystemEntry | None = None
    encoding: str = "utf-8"
    workspace_only: bool | None = True


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
    """File reading failed. Common causes: file not found, permission denied, encoding error."""


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
    """File/directory creation failed."""


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
    """File/directory rename failed."""
