"""Path resolution utilities for file operations.

Provides cross-platform path handling including:
- Path sanitization (shell escapes, quotes, newlines)
- Path expansion (tilde, environment variables, Windows special folders)
- Path resolution (relative to workspace)
- Platform normalization (Windows long paths, etc.)

These utilities are used by both OSManager and FileReadDrivers for consistent
path handling across the codebase.
"""

import os
import re
from pathlib import Path


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
    # Convert Path objects to strings
    if isinstance(path, Path):
        path = str(path)

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
    import sys

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
    """Expand a path string, handling tilde and environment variables.

    Expands ~ to user home directory and environment variables like $HOME or %USERPROFILE%.

    Note: This is a simplified version that doesn't handle Windows special folders.
    For full Windows special folder support, use OSManager._expand_path().

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
