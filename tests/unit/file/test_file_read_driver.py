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
