"""Read-only file loader for multi-backend sources."""

from __future__ import annotations

from dataclasses import dataclass

from griptape_nodes.file.loader_driver import LoaderDriverRegistry


@dataclass
class FileLoader:
    """Read-only file loader for multi-backend sources.

    Loads files from any backend: local paths, HTTP URLs, S3 buckets,
    Griptape Cloud, or data URIs. Uses LoaderDriver abstraction to
    handle different location formats.

    For WRITING files, use OSManager directly (all saves go to local filesystem).

    Examples:
        # Local file
        loader = FileLoader(location="/tmp/test.txt")
        data = await loader.read()

        # HTTP URL
        loader = FileLoader(location="https://example.com/image.png")
        image_data = await loader.read()

        # S3 bucket
        loader = FileLoader(location="s3://bucket/key.txt")
        s3_data = await loader.read()

        # Data URI
        loader = FileLoader(location="data:image/png;base64,...")
        decoded_data = await loader.read()
    """

    location: str  # "/path/to/file", "s3://bucket/key", "https://...", etc.

    async def read(self, timeout: float = 120.0) -> bytes:
        """Read bytes from location.

        Args:
            timeout: Timeout in seconds for the operation (default: 120)

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: File does not exist
            TimeoutError: Operation exceeded timeout
            PermissionError: No permission to read file
        """
        driver = LoaderDriverRegistry.get_driver(self.location)
        return await driver.read(self.location, timeout)

    async def exists(self) -> bool:
        """Check if file exists and is readable.

        Returns:
            True if file exists and is readable
        """
        driver = LoaderDriverRegistry.get_driver(self.location)
        return await driver.exists(self.location)

    @property
    def size(self) -> int:
        """File size in bytes.

        Raises:
            FileNotFoundError: File does not exist
        """
        driver = LoaderDriverRegistry.get_driver(self.location)
        return driver.get_size(self.location)
