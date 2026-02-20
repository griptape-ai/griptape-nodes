"""Path utilities for file operations.

Comprehensive path handling utilities including:
- Path sanitization (shell escapes, quotes, newlines)
- Path expansion (tilde, environment variables)
- Path resolution (relative paths, cross-platform)
- Path normalization (Windows long paths, etc.)
- Workspace operations (relative path conversions)
- file:// URI parsing

These utilities provide consistent path handling across the codebase
and are used by OSManager, FileDrivers, and workspace managers.
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


def parse_filename_components(filename: str, default_extension: str = "png") -> tuple[str, str]:
    """Parse filename into base and extension.

    Args:
        filename: Filename to parse (e.g., "image.png", "output.tar.gz", "test")
        default_extension: Extension to use if filename has none

    Returns:
        Tuple of (base, extension) where extension has no leading dot

    Examples:
        parse_filename_components("image.png")
        -> ("image", "png")

        parse_filename_components("output.tar.gz")
        -> ("output.tar", "gz")

        parse_filename_components("test")
        -> ("test", "png")
    """
    path = Path(filename)
    if path.suffix:
        return path.stem, path.suffix.lstrip(".")
    return str(path), default_extension


def parse_file_uri(location: str) -> str | None:
    """Parse file:// URI and return local path, or None if not a valid file URI.

    Supports:
    - file:///path/to/file (Unix absolute path)
    - file://localhost/path/to/file (localhost)
    - file:///C:/path/to/file (Windows absolute path)

    Rejects:
    - file://hostname/path (non-localhost network paths)

    Args:
        location: Location string to parse

    Returns:
        Local file path if valid file:// URI, None otherwise

    Examples:
        parse_file_uri("file:///path/to/file.txt")
        -> "/path/to/file.txt"

        parse_file_uri("file://localhost/path/to/file.txt")
        -> "/path/to/file.txt"

        parse_file_uri("file:///C:/Users/test/file.txt")
        -> "C:/Users/test/file.txt"

        parse_file_uri("file:///path/with%20spaces.txt")
        -> "/path/with spaces.txt"

        parse_file_uri("file://remote-server/path")
        -> None
    """
    if not location.startswith("file://"):
        return None

    parsed = urlparse(location)

    if parsed.scheme != "file":
        return None

    # Reject non-localhost network paths
    if parsed.netloc and parsed.netloc.lower() not in ("", "localhost"):
        return None

    # Get the path component and decode percent-encoding
    path = unquote(parsed.path)

    # Windows paths in file:// URIs have format file:///C:/path
    # Unix paths have format file:///path
    # The path component includes the leading slash, so we need to handle Windows specially
    if path.startswith("/") and len(path) > 2 and path[2] == ":":  # noqa: PLR2004
        # Windows path like /C:/Users/... -> C:/Users/...
        path = path[1:]

    return path


def sanitize_path_string(path: str | Path) -> str:
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
        path: Path string or Path object to sanitize

    Returns:
        Sanitized path string
    """
    # Convert Path objects to strings using POSIX format for cross-platform consistency
    if isinstance(path, Path):
        path = path.as_posix()

    if not isinstance(path, str):
        return path

    # First, strip surrounding quotes
    path_str = strip_surrounding_quotes(path)

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


def strip_surrounding_quotes(path: str) -> str:
    """Remove surrounding quotes from path string.

    Args:
        path: Path string that may be quoted

    Returns:
        Path string without surrounding quotes
    """
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        return path[1:-1]
    return path


def normalize_path_for_platform(path: Path) -> str:
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
    # Windows MAX_PATH limit - paths longer than this need \\?\ prefix
    windows_max_path = 260

    path_str = str(path.resolve())

    # Clean path to remove newlines/carriage returns, shell escapes, and quotes
    # This handles cases where merge_texts nodes accidentally add newlines between path components
    path_str = sanitize_path_string(path_str)

    # Windows long path handling (paths > windows_max_path chars need \\?\ prefix)
    if sys.platform.startswith("win") and len(path_str) >= windows_max_path and not path_str.startswith("\\\\?\\"):
        # UNC paths (\\server\share) need \\?\UNC\ prefix
        if path_str.startswith("\\\\"):
            return f"\\\\?\\UNC\\{path_str[2:]}"
        # Regular paths need \\?\ prefix
        return f"\\\\?\\{path_str}"

    return path_str


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in a path string.

    Handles tilde (~) expansion and environment variables ($HOME, %USERPROFILE%, etc.)
    for standard path expansion scenarios.

    Note: This function does NOT resolve Windows special folders (Desktop, Downloads,
    etc.) via Shell API. For workspace-aware path resolution with Windows special
    folder support, use OSManager methods instead.

    Args:
        path_str: Path string that may contain ~ or environment variables

    Returns:
        Expanded Path object

    Examples:
        expand_path("~/Documents")
        -> Path("/Users/username/Documents")

        expand_path("$HOME/file.txt")
        -> Path("/Users/username/file.txt")
    """
    expanded_vars = os.path.expandvars(path_str)
    expanded_user = os.path.expanduser(expanded_vars)  # noqa: PTH111
    return Path(expanded_user)


def path_needs_expansion(path_str: str) -> bool:
    """Return True if path contains env vars, is absolute, or starts with ~ (needs expand_path).

    Args:
        path_str: Path string to check

    Returns:
        True if path needs expansion
    """
    has_env_vars = "%" in path_str or "$" in path_str
    is_absolute = Path(path_str).is_absolute()
    starts_with_tilde = path_str.startswith("~")
    return has_env_vars or is_absolute or starts_with_tilde


def resolve_path_safely(path: Path) -> Path:
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


def resolve_file_path(path_str: str, base_dir: Path) -> Path:
    """Resolve a file path, handling absolute, relative, and tilde paths.

    Args:
        path_str: Path string that may be absolute, relative, or start with ~
        base_dir: Base directory for resolving relative paths

    Returns:
        Resolved Path object
    """
    if path_needs_expansion(path_str):
        return expand_path(path_str)
    return resolve_path_safely(base_dir / path_str)


def resolve_workspace_path(path: Path, base_directory: Path) -> Path:
    """Resolve a path, treating relative paths as relative to a base directory.

    If the path is relative, it's resolved relative to the base directory.
    If the path is absolute, it's resolved as-is.

    This utility works with any base directory - workspace_directory, project_base_dir,
    or any other base path.

    Args:
        path: The path to resolve (can be relative or absolute)
        base_directory: The base directory to use for relative paths

    Returns:
        The resolved absolute path

    Example:
        >>> base = Path("/workspace")
        >>> resolve_workspace_path(Path("file.txt"), base)
        Path("/workspace/file.txt")
        >>> resolve_workspace_path(Path("/tmp/file.txt"), base)
        Path("/tmp/file.txt")
    """
    if not path.is_absolute():
        return (base_directory / path).resolve()
    return path.resolve()


def get_workspace_relative_path(path: Path, base_directory: Path) -> Path:
    """Convert a path to be relative to a base directory.

    Takes an absolute or relative path and returns it as a path relative to
    the base directory.

    This utility works with any base directory - workspace_directory, project_base_dir,
    or any other base path.

    Args:
        path: The path to convert (can be relative or absolute)
        base_directory: The base directory to make the path relative to

    Returns:
        Path relative to base_directory

    Example:
        >>> base = Path("/workspace")
        >>> get_workspace_relative_path(Path("/workspace/subdir/file.txt"), base)
        Path("subdir/file.txt")
        >>> get_workspace_relative_path(Path("file.txt"), base)
        Path("file.txt")
    """
    absolute_path = resolve_workspace_path(path, base_directory)
    return absolute_path.relative_to(base_directory.resolve())
