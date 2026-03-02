"""Unit tests for FileDriver and FileDriverRegistry."""

from typing import Any

import pytest

from griptape_nodes.files.file_driver import (
    FileDriver,
    FileDriverNotFoundError,
    FileDriverRegistry,
)


class MockDriver(FileDriver):
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


class MockDriverWithPriority(FileDriver):
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


class TestFileDriverRegistry:
    """Tests for FileDriverRegistry class."""

    def test_register_driver(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test registering a driver."""
        driver = MockDriver("http://")
        FileDriverRegistry.register(driver)
        assert len(FileDriverRegistry._drivers) == 1

    def test_get_driver_returns_first_match(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that get_driver returns the first matching driver."""
        http_driver = MockDriver("http://")
        https_driver = MockDriver("https://")
        FileDriverRegistry.register(http_driver)
        FileDriverRegistry.register(https_driver)

        result = FileDriverRegistry.get_driver("http://example.com")
        assert result is http_driver

    def test_get_driver_respects_order(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that driver registration order is respected."""
        generic_driver = MockDriver("h")  # Matches http:// and https://
        specific_driver = MockDriver("https://")  # Only matches https://

        # Register generic first, then specific
        FileDriverRegistry.register(generic_driver)
        FileDriverRegistry.register(specific_driver)

        # Generic should match first (even for https://)
        result = FileDriverRegistry.get_driver("https://example.com")
        assert result is generic_driver

    def test_get_driver_raises_when_no_match(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that get_driver raises when no driver matches."""
        driver = MockDriver("http://")
        FileDriverRegistry.register(driver)

        test_location = "ftp://example.com"
        with pytest.raises(FileDriverNotFoundError) as exc_info:
            FileDriverRegistry.get_driver(test_location)

        error_message = str(exc_info.value)
        assert "No file driver found" in error_message
        assert f"location: {test_location}" in error_message

    def test_clear_removes_all_drivers(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that clear removes all registered drivers."""
        FileDriverRegistry.register(MockDriver("http://"))
        FileDriverRegistry.register(MockDriver("https://"))
        expected_driver_count = 2
        assert len(FileDriverRegistry._drivers) == expected_driver_count

        FileDriverRegistry.clear()
        assert len(FileDriverRegistry._drivers) == 0

    def test_multiple_drivers_with_overlapping_patterns(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test registry with multiple drivers that could match the same location."""
        # Register in order of specificity
        data_driver = MockDriver("data:")
        http_driver = MockDriver("http")  # Matches both http:// and https://
        local_driver = MockDriver("/")  # Matches absolute paths

        FileDriverRegistry.register(data_driver)
        FileDriverRegistry.register(http_driver)
        FileDriverRegistry.register(local_driver)

        # Test each driver is selected correctly
        assert FileDriverRegistry.get_driver("data:image/png") is data_driver
        assert FileDriverRegistry.get_driver("http://example.com") is http_driver
        assert FileDriverRegistry.get_driver("https://example.com") is http_driver
        assert FileDriverRegistry.get_driver("/path/to/file") is local_driver


class TestFileDriverPriority:
    """Tests for FileDriver priority system."""

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

        FileDriverRegistry.register(high_priority_driver)
        FileDriverRegistry.register(medium_priority_driver)
        FileDriverRegistry.register(low_priority_driver)

        # Verify drivers are sorted by priority (lowest first)
        drivers = FileDriverRegistry._drivers
        assert len(drivers) == 3  # noqa: PLR2004
        assert drivers[0] is low_priority_driver
        assert drivers[1] is medium_priority_driver
        assert drivers[2] is high_priority_driver

    def test_lower_priority_drivers_checked_first(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that lower priority drivers are checked before higher priority ones."""
        # Both drivers match "test://", but low priority should match first
        low_priority_driver = MockDriverWithPriority("test", priority=10)
        high_priority_driver = MockDriverWithPriority("test", priority=100)

        FileDriverRegistry.register(high_priority_driver)
        FileDriverRegistry.register(low_priority_driver)

        result = FileDriverRegistry.get_driver("test://example")
        assert result is low_priority_driver

    def test_fallback_driver_with_high_priority_checked_last(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that fallback drivers with high priority are checked last."""
        # Specific driver with low priority
        specific_driver = MockDriverWithPriority("http://", priority=10)
        # Fallback driver that matches everything with high priority
        fallback_driver = MockDriverWithPriority("", priority=100)

        FileDriverRegistry.register(fallback_driver)
        FileDriverRegistry.register(specific_driver)

        # Specific driver should match first even though fallback was registered first
        result = FileDriverRegistry.get_driver("http://example.com")
        assert result is specific_driver

    def test_local_file_driver_has_high_priority(self) -> None:
        """Test that LocalFileDriver has priority 100."""
        from griptape_nodes.files.drivers.local_file_driver import LocalFileDriver

        driver = LocalFileDriver()
        assert driver.priority == 100  # noqa: PLR2004

    def test_priority_sorting_preserves_order_for_equal_priorities(self, clear_registry: Any) -> None:  # noqa: ARG002
        """Test that drivers with equal priority maintain registration order."""
        driver1 = MockDriverWithPriority("a", priority=50)
        driver2 = MockDriverWithPriority("b", priority=50)
        driver3 = MockDriverWithPriority("c", priority=50)

        FileDriverRegistry.register(driver1)
        FileDriverRegistry.register(driver2)
        FileDriverRegistry.register(driver3)

        drivers = FileDriverRegistry._drivers
        assert drivers[0] is driver1
        assert drivers[1] is driver2
        assert drivers[2] is driver3
