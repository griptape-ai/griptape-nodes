"""Registry for file drivers."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from griptape_nodes.file.base_file_driver import BaseFileDriver


class FileDriverNotFoundError(Exception):
    """No file driver found for the given location."""


class FileDriverRegistry:
    """Singleton registry for file drivers.

    Drivers are automatically sorted by priority (lowest first).
    Specific drivers (HTTP, data URI, cloud) should have low priority (default: 50).
    Fallback drivers (LocalFileDriver) should have high priority (100+).
    """

    _drivers: ClassVar[list[BaseFileDriver]] = []

    @classmethod
    def register(cls, driver: BaseFileDriver) -> None:
        """Register a file driver (automatically sorted by priority).

        Drivers are sorted by priority on registration:
        - Lower priority values are checked first (specific drivers)
        - Higher priority values are checked last (fallback drivers)

        Args:
            driver: The file driver to register
        """
        cls._drivers.append(driver)
        # Sort by priority (lowest first) to ensure fallback drivers are checked last
        cls._drivers.sort(key=lambda d: d.priority)

    @classmethod
    def get_driver(cls, location: str) -> BaseFileDriver:
        """Get first driver that can handle this location.

        Args:
            location: The location string to find a driver for

        Returns:
            The first driver that can handle this location

        Raises:
            FileDriverNotFoundError: No driver can handle this location
        """
        for driver in cls._drivers:
            if driver.can_handle(location):
                return driver

        msg = (
            f"No file driver found for location: {location}. "
            f"Registered drivers: {[type(d).__name__ for d in cls._drivers]}"
        )
        raise FileDriverNotFoundError(msg)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered drivers (for testing)."""
        cls._drivers = []
