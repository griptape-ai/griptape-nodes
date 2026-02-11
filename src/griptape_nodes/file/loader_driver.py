"""Loader driver interface for reading files from various sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class LoaderDriver(ABC):
    """Abstract loader driver for reading files from different backends.

    Each driver handles a specific type of location (local paths, HTTP URLs,
    S3 buckets, cloud URLs, data URIs). Drivers are registered with
    LoaderDriverRegistry and selected based on the location format.

    LoaderDrivers are READ-ONLY. For writing files, use OSManager directly
    (all saves go to local filesystem).
    """

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
    async def read(self, location: str, timeout: float) -> bytes:
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


class LoaderDriverNotFoundError(Exception):
    """No loader driver found for the given location."""


class LoaderDriverRegistry:
    """Singleton registry for loader drivers.

    Drivers are registered in order of specificity (most specific first).
    LocalLoaderDriver should be registered last as it matches all absolute paths.
    """

    _drivers: ClassVar[list[LoaderDriver]] = []

    @classmethod
    def register(cls, driver: LoaderDriver) -> None:
        """Register a loader driver (order matters - first match wins).

        Args:
            driver: The loader driver to register
        """
        cls._drivers.append(driver)

    @classmethod
    def get_driver(cls, location: str) -> LoaderDriver:
        """Get first driver that can handle this location.

        Args:
            location: The location string to find a driver for

        Returns:
            The first driver that can handle this location

        Raises:
            LoaderDriverNotFoundError: No driver can handle this location
        """
        for driver in cls._drivers:
            if driver.can_handle(location):
                return driver

        msg = (
            f"No loader driver found for location: {location}. "
            f"Registered drivers: {[type(d).__name__ for d in cls._drivers]}"
        )
        raise LoaderDriverNotFoundError(msg)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered drivers (for testing)."""
        cls._drivers = []
