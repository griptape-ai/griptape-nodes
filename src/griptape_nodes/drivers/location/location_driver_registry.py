"""Registry for file location loading drivers."""

from typing import ClassVar

from griptape_nodes.drivers.location.base_location_driver import BaseLocationDriver
from griptape_nodes.utils.metaclasses import SingletonMeta


class LocationDriverRegistry(metaclass=SingletonMeta):
    """Registry for file location loading drivers.

    Provides centralized registration and lookup of location drivers.
    Follows singleton pattern to ensure single registry instance.

    Drivers are selected using first-match-wins: the first registered driver
    whose can_handle() returns True will be used.
    """

    _drivers: ClassVar[list[BaseLocationDriver]] = []

    @classmethod
    def register_driver(cls, driver: BaseLocationDriver) -> None:
        """Register a location driver.

        Order matters - first match wins when selecting drivers.

        Args:
            driver: Driver instance to register
        """
        instance = cls()
        instance._drivers.append(driver)

    @classmethod
    def get_driver_for_location(cls, location: str) -> BaseLocationDriver | None:
        """Get the first driver that can handle the given location.

        Args:
            location: Location string to find driver for

        Returns:
            Driver instance or None if no driver can handle location
        """
        instance = cls()
        for driver in instance._drivers:
            if driver.can_handle(location):
                return driver
        return None

    @classmethod
    def list_drivers(cls) -> list[BaseLocationDriver]:
        """List all registered drivers in registration order.

        Returns:
            Copy of drivers list (for debugging/testing)
        """
        instance = cls()
        return instance._drivers.copy()
