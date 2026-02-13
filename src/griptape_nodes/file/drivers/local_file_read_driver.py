"""File read driver for local filesystem locations."""

from pathlib import Path

from griptape_nodes.file.base_file_read_driver import BaseFileReadDriver
from griptape_nodes.file.path_utils import (
    expand_path,
    normalize_path_for_platform,
    parse_file_uri,
    path_needs_expansion,
    sanitize_path_string,
)


class LocalFileReadDriver(BaseFileReadDriver):
    """File read driver for local filesystem locations.

    Reads files from local filesystem paths with full validation.
    For writing files, use OSManager directly.

    This driver should be registered LAST in FileReadDriverRegistry as it matches all
    absolute paths and file:// URIs (fallback driver).
    """

    def can_handle(self, location: str) -> bool:
        """Check if location is a local file path or file:// URI.

        Args:
            location: Location string to check

        Returns:
            True for absolute paths and file:// URIs (this is the fallback driver)
        """
        # Handle file:// URIs
        if location.startswith("file://"):
            return parse_file_uri(location) is not None

        # Handle absolute paths
        path = Path(location)
        return path.is_absolute()

    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        """Read file from local filesystem with validation.

        Performs:
        - file:// URI parsing (if applicable)
        - Path sanitization (shell escapes, quotes)
        - Path expansion (~/env vars)
        - Existence check
        - Is-file check (not directory)
        - Permission check

        Args:
            location: Absolute file path, file:// URI, or path with ~
            timeout: Ignored for local files

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: File does not exist
            IsADirectoryError: Path is a directory
            PermissionError: No read permission
            ValueError: Invalid file:// URI
        """
        # 0. Convert file:// URI to path if needed
        if location.startswith("file://"):
            parsed_path = parse_file_uri(location)
            if parsed_path is None:
                msg = f"Invalid file:// URI: {location}"
                raise ValueError(msg)
            location = parsed_path

        # 1. Sanitize path (remove shell escapes, quotes from Finder)
        clean_location = sanitize_path_string(location)

        # 2. Expand path (~/env vars)
        if path_needs_expansion(clean_location):
            path = expand_path(clean_location)
        else:
            path = Path(clean_location)

        # 3. Normalize for platform (Windows long paths, etc.)
        normalized_path = Path(normalize_path_for_platform(path))

        # 4. Validate existence
        if not normalized_path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        # 5. Validate is file (not directory)
        if not normalized_path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        # 6. Read file
        return normalized_path.read_bytes()

    async def exists(self, location: str) -> bool:
        """Check if file exists on local filesystem.

        Args:
            location: Absolute file path or file:// URI

        Returns:
            True if file exists and is a file (not directory)
        """
        # 0. Convert file:// URI to path if needed
        if location.startswith("file://"):
            parsed_path = parse_file_uri(location)
            if parsed_path is None:
                return False
            location = parsed_path

        # 1. Sanitize path (remove shell escapes, quotes from Finder)
        clean_location = sanitize_path_string(location)

        # 2. Expand path (~/env vars)
        if path_needs_expansion(clean_location):
            path = expand_path(clean_location)
        else:
            path = Path(clean_location)

        # 3. Check existence
        return path.exists() and path.is_file()

    def get_size(self, location: str) -> int:
        """Get file size from local filesystem.

        Args:
            location: Absolute file path or file:// URI

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: File does not exist
            ValueError: Invalid file:// URI
        """
        # 0. Convert file:// URI to path if needed
        if location.startswith("file://"):
            parsed_path = parse_file_uri(location)
            if parsed_path is None:
                msg = f"Invalid file:// URI: {location}"
                raise ValueError(msg)
            location = parsed_path

        # 1. Sanitize path (remove shell escapes, quotes from Finder)
        clean_location = sanitize_path_string(location)

        # 2. Expand path (~/env vars)
        if path_needs_expansion(clean_location):
            path = expand_path(clean_location)
        else:
            path = Path(clean_location)

        # 3. Validate existence
        if not path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        return path.stat().st_size
