"""Base file driver interface for reading files from various sources."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseFileDriver(ABC):
    """Abstract file driver for reading files from different backends.

    Each driver handles a specific type of location (local paths, HTTP URLs,
    S3 buckets, cloud URLs, data URIs). Drivers are registered with
    FileDriverRegistry and selected based on the location format.

    Driver Priority:
    - Drivers are checked in order of priority (lowest to highest)
    - Lower priority values are checked first (specific drivers)
    - Higher priority values are checked last (fallback drivers)
    - Default priority is 50 for most drivers
    - LocalFileDriver should use priority 100 (checked last)
    """

    @property
    def priority(self) -> int:
        """Priority for driver selection (lower = checked first, higher = checked last).

        Returns:
            Priority value (default: 50)
        """
        return 50

    @abstractmethod
    def can_handle(self, location: str) -> bool:
        """Check if this driver handles this location format.

        Examples:
        - LocalStorageDriver: True for absolute paths
        - HttpStorageDriver: True for http:// and https://
        - S3StorageDriver: True for s3://
        - CloudStorageDriver: True for cloud.griptape.ai URLs

        Args:
            location: The location string to check

        Returns:
            True if this driver can handle the location
        """

    @abstractmethod
    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ASYNC109
        """Read bytes from location.

        Args:
            location: The location to read from
            timeout: Timeout in seconds for the operation

        Returns:
            The file contents as bytes

        Raises:
            FileNotFoundError: Location does not exist
            TimeoutError: Operation exceeded timeout
            PermissionError: No permission to read location
        """

    @abstractmethod
    async def exists(self, location: str) -> bool:
        """Check if location exists and is readable.

        Args:
            location: The location to check

        Returns:
            True if the location exists and is readable
        """

    @abstractmethod
    def get_size(self, location: str) -> int:
        """Get file size in bytes (may be sync operation).

        Args:
            location: The location to get size for

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: Location does not exist
        """
