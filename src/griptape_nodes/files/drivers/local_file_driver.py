"""File driver for local filesystem locations."""

from pathlib import Path

from griptape_nodes.files.base_file_driver import BaseFileDriver
from griptape_nodes.files.path_utils import (
    expand_path,
    normalize_path_for_platform,
    parse_file_uri,
    path_needs_expansion,
    sanitize_path_string,
)


class LocalFileDriver(BaseFileDriver):
    """File driver for local filesystem locations.

    Reads files from local filesystem paths with full validation.
    For writing files, use OSManager directly.

    This driver is automatically registered last (priority 100) as it matches all
    absolute paths and file:// URIs (fallback driver).
    """

    @property
    def priority(self) -> int:
        """Return high priority (100) to ensure this driver is checked last.

        Returns:
            Priority value of 100 (checked after all other drivers)
        """
        return 100

    def can_handle(self, location: str) -> bool:  # noqa: ARG002
        """Always returns True — this is the fallback driver.

        Since this driver has the highest priority value (checked last),
        any location that wasn't matched by a more specific driver is
        assumed to be a local file path.

        Args:
            location: Location string to check

        Returns:
            Always True
        """
        return True

    def _resolve_path(self, location: str) -> Path:
        """Resolve a location string to a local filesystem Path.

        Handles file:// URI parsing, path sanitization, expansion, and
        platform normalization.

        Args:
            location: Absolute file path, file:// URI, or path with ~

        Returns:
            Resolved Path object

        Raises:
            ValueError: Invalid file:// URI or empty location
        """
        if not location or not location.strip():
            msg = f"Empty file path: {location!r}"
            raise ValueError(msg)

        # Convert file:// URI to path if needed
        if location.startswith("file://"):
            parsed_path = parse_file_uri(location)
            if parsed_path is None:
                msg = f"Invalid file:// URI: {location}"
                raise ValueError(msg)
            location = parsed_path

        # Sanitize path (remove shell escapes, quotes from Finder)
        clean_location = sanitize_path_string(location)

        # Expand path (~/env vars)
        if path_needs_expansion(clean_location):
            path = expand_path(clean_location)
        else:
            path = Path(clean_location)

        # Normalize for platform (Windows long paths, etc.)
        return Path(normalize_path_for_platform(path))

    # TODO: Replace pathlib.Path with anyio.Path for async compatibility https://github.com/griptape-ai/griptape-nodes/issues/3959
    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        """Read file from local filesystem with validation.

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
        path = self._resolve_path(location)

        if not path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        return path.read_bytes()

    async def exists(self, location: str) -> bool:
        """Check if file exists on local filesystem.

        Args:
            location: Absolute file path or file:// URI

        Returns:
            True if file exists and is a file (not directory)
        """
        try:
            path = self._resolve_path(location)
        except ValueError:
            return False

        return path.exists() and path.is_file()

    def get_size(self, location: str) -> int:
        """Get file size from local filesystem.

        Args:
            location: Absolute file path or file:// URI

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: File does not exist
            IsADirectoryError: Path is a directory
            ValueError: Invalid file:// URI
        """
        path = self._resolve_path(location)

        if not path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        return path.stat().st_size
