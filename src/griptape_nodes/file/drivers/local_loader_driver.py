"""Loader driver for local filesystem locations."""

from pathlib import Path

from griptape_nodes.file.loader_driver import LoaderDriver


class LocalLoaderDriver(LoaderDriver):
    """Loader driver for local filesystem locations.

    Reads files from local filesystem paths. For writing files, use OSManager directly.

    This driver should be registered LAST in LoaderDriverRegistry as it matches all
    absolute paths (fallback driver).
    """

    def can_handle(self, location: str) -> bool:
        """Check if location is a local file path.

        Args:
            location: Location string to check

        Returns:
            True for absolute paths (this is the fallback driver)
        """
        path = Path(location)
        return path.is_absolute()

    async def read(self, location: str, _timeout: float) -> bytes:
        """Read file from local filesystem.

        Args:
            location: Absolute file path
            _timeout: Ignored for local files

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: File does not exist
            PermissionError: No permission to read file
        """
        path = Path(location)

        if not path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        # Lazy import required: circular dependency between this module and GriptapeNodes
        # file_loader imports drivers at module level, which instantiates this driver
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Get OS Manager for path normalization
        os_manager = GriptapeNodes.OSManager()
        normalized_path = os_manager.normalize_path_for_platform(path)

        # Read file
        return Path(normalized_path).read_bytes()

    async def exists(self, location: str) -> bool:
        """Check if file exists on local filesystem.

        Args:
            location: Absolute file path

        Returns:
            True if file exists and is a file (not directory)
        """
        path = Path(location)
        return path.exists() and path.is_file()

    def get_size(self, location: str) -> int:
        """Get file size from local filesystem.

        Args:
            location: Absolute file path

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: File does not exist
        """
        path = Path(location)

        if not path.exists():
            msg = f"File not found: {location}"
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Path is a directory, not a file: {location}"
            raise IsADirectoryError(msg)

        return path.stat().st_size
