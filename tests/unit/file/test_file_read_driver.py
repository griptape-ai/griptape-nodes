"""Unit tests for FileReadDriver and FileReadDriverRegistry."""

from typing import Any

import pytest

from griptape_nodes.file.file_read_driver import (
    FileReadDriver,
    FileReadDriverNotFoundError,
    FileReadDriverRegistry,
)


class MockDriver(FileReadDriver):
    """Mock driver for testing."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def can_handle(self, location: str) -> bool:
        return location.startswith(self.prefix)

    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        return f"Mock read: {location}".encode()

    async def exists(self, location: str) -> bool:  # noqa: ARG002
        return True

    def get_size(self, location: str) -> int:  # noqa: ARG002
        return 100


class MockDriverWithPriority(FileReadDriver):
    """Mock driver with custom priority for testing."""

    def __init__(self, prefix: str, priority: int) -> None:
        self.prefix = prefix
        self._priority = priority

    @property
    def priority(self) -> int:
        return self._priority

    def can_handle(self, location: str) -> bool:
        return location.startswith(self.prefix)

    async def read(self, location: str, timeout: float) -> bytes:  # noqa: ARG002, ASYNC109
        return f"Mock read: {location}".encode()

    async def exists(self, location: str) -> bool:  # noqa: ARG002
        return True

    def get_size(self, location: str) -> int:  # noqa: ARG002
        return 100


class TestFileReadDriverRegistry:
    """Tests for FileReadDriverRegistry class."""

    def test_register_driver(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test registering a driver."""
        driver = MockDriver("http://")
        FileReadDriverRegistry.register(driver)
        assert len(FileReadDriverRegistry._drivers) == 1

    def test_get_driver_returns_first_match(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that get_driver returns the first matching driver."""
        http_driver = MockDriver("http://")
        https_driver = MockDriver("https://")
        FileReadDriverRegistry.register(http_driver)
        FileReadDriverRegistry.register(https_driver)

        result = FileReadDriverRegistry.get_driver("http://example.com")
        assert result is http_driver

    def test_get_driver_respects_order(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that driver registration order is respected."""
        generic_driver = MockDriver("h")  # Matches http:// and https://
        specific_driver = MockDriver("https://")  # Only matches https://

        # Register generic first, then specific
        FileReadDriverRegistry.register(generic_driver)
        FileReadDriverRegistry.register(specific_driver)

        # Generic should match first (even for https://)
        result = FileReadDriverRegistry.get_driver("https://example.com")
        assert result is generic_driver

    def test_get_driver_raises_when_no_match(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that get_driver raises when no driver matches."""
        driver = MockDriver("http://")
        FileReadDriverRegistry.register(driver)

        test_location = "ftp://example.com"
        with pytest.raises(FileReadDriverNotFoundError) as exc_info:
            FileReadDriverRegistry.get_driver(test_location)

        error_message = str(exc_info.value)
        assert "No file read driver found" in error_message
        assert f"location: {test_location}" in error_message

    def test_clear_removes_all_drivers(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that clear removes all registered drivers."""
        FileReadDriverRegistry.register(MockDriver("http://"))
        FileReadDriverRegistry.register(MockDriver("https://"))
        expected_driver_count = 2
        assert len(FileReadDriverRegistry._drivers) == expected_driver_count

        FileReadDriverRegistry.clear()
        assert len(FileReadDriverRegistry._drivers) == 0

    def test_multiple_drivers_with_overlapping_patterns(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test registry with multiple drivers that could match the same location."""
        # Register in order of specificity
        data_driver = MockDriver("data:")
        http_driver = MockDriver("http")  # Matches both http:// and https://
        local_driver = MockDriver("/")  # Matches absolute paths

        FileReadDriverRegistry.register(data_driver)
        FileReadDriverRegistry.register(http_driver)
        FileReadDriverRegistry.register(local_driver)

        # Test each driver is selected correctly
        assert FileReadDriverRegistry.get_driver("data:image/png") is data_driver
        assert FileReadDriverRegistry.get_driver("http://example.com") is http_driver
        assert FileReadDriverRegistry.get_driver("https://example.com") is http_driver
        assert FileReadDriverRegistry.get_driver("/path/to/file") is local_driver


class TestFileReadDriverPriority:
    """Tests for FileReadDriver priority system."""

    def test_default_priority_is_50(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that default driver priority is 50."""
        driver = MockDriver("http://")
        assert driver.priority == 50  # noqa: PLR2004

    def test_drivers_sorted_by_priority_on_registration(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that drivers are automatically sorted by priority when registered."""
        # Register in reverse priority order
        high_priority_driver = MockDriverWithPriority("high", priority=100)
        medium_priority_driver = MockDriverWithPriority("med", priority=50)
        low_priority_driver = MockDriverWithPriority("low", priority=10)

        FileReadDriverRegistry.register(high_priority_driver)
        FileReadDriverRegistry.register(medium_priority_driver)
        FileReadDriverRegistry.register(low_priority_driver)

        # Verify drivers are sorted by priority (lowest first)
        drivers = FileReadDriverRegistry._drivers
        assert len(drivers) == 3  # noqa: PLR2004
        assert drivers[0] is low_priority_driver
        assert drivers[1] is medium_priority_driver
        assert drivers[2] is high_priority_driver

    def test_lower_priority_drivers_checked_first(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that lower priority drivers are checked before higher priority ones."""
        # Both drivers match "test://", but low priority should match first
        low_priority_driver = MockDriverWithPriority("test", priority=10)
        high_priority_driver = MockDriverWithPriority("test", priority=100)

        FileReadDriverRegistry.register(high_priority_driver)
        FileReadDriverRegistry.register(low_priority_driver)

        result = FileReadDriverRegistry.get_driver("test://example")
        assert result is low_priority_driver

    def test_fallback_driver_with_high_priority_checked_last(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that fallback drivers with high priority are checked last."""
        # Specific driver with low priority
        specific_driver = MockDriverWithPriority("http://", priority=10)
        # Fallback driver that matches everything with high priority
        fallback_driver = MockDriverWithPriority("", priority=100)

        FileReadDriverRegistry.register(fallback_driver)
        FileReadDriverRegistry.register(specific_driver)

        # Specific driver should match first even though fallback was registered first
        result = FileReadDriverRegistry.get_driver("http://example.com")
        assert result is specific_driver

    def test_local_file_driver_has_high_priority(self) -> None:
        """Test that LocalFileReadDriver has priority 100."""
        from griptape_nodes.file.drivers.local_file_read_driver import LocalFileReadDriver

        driver = LocalFileReadDriver()
        assert driver.priority == 100  # noqa: PLR2004

    def test_priority_sorting_preserves_order_for_equal_priorities(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that drivers with equal priority maintain registration order."""
        driver1 = MockDriverWithPriority("a", priority=50)
        driver2 = MockDriverWithPriority("b", priority=50)
        driver3 = MockDriverWithPriority("c", priority=50)

        FileReadDriverRegistry.register(driver1)
        FileReadDriverRegistry.register(driver2)
        FileReadDriverRegistry.register(driver3)

        drivers = FileReadDriverRegistry._drivers
        assert drivers[0] is driver1
        assert drivers[1] is driver2
        assert drivers[2] is driver3
