"""Unit tests for DataUriFileDriver."""

import base64

import pytest

from griptape_nodes.files.drivers.data_uri_file_driver import DataUriFileDriver


class TestDataUriFileDriver:
    """Tests for DataUriFileDriver class."""

    @pytest.fixture
    def driver(self) -> DataUriFileDriver:
        """Create a DataUriFileDriver instance."""
        return DataUriFileDriver()

    @pytest.fixture
    def sample_data_uri(self) -> str:
        """Create a sample data URI."""
        content = b"Hello, World!"
        encoded = base64.b64encode(content).decode("utf-8")
        return f"data:text/plain;base64,{encoded}"

    @pytest.fixture
    def sample_image_uri(self) -> str:
        """Create a sample image data URI (1x1 transparent PNG)."""
        png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        return f"data:image/png;base64,{png_data}"

    def test_can_handle_data_uris(self, driver: DataUriFileDriver) -> None:
        """Test that driver handles data URIs."""
        assert driver.can_handle("data:image/png;base64,abc") is True
        assert driver.can_handle("data:text/plain;base64,def") is True

    def test_can_handle_rejects_other_schemes(self, driver: DataUriFileDriver) -> None:
        """Test that driver rejects non-data-URI schemes."""
        assert driver.can_handle("http://example.com/file.txt") is False
        assert driver.can_handle("https://example.com/file.txt") is False
        assert driver.can_handle("/local/path/file.txt") is False

    @pytest.mark.asyncio
    async def test_read_valid_data_uri(self, driver: DataUriFileDriver, sample_data_uri: str) -> None:
        """Test reading a valid data URI."""
        content = await driver.read(sample_data_uri, timeout=0)
        assert content == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_read_image_data_uri(self, driver: DataUriFileDriver, sample_image_uri: str) -> None:
        """Test reading an image data URI."""
        content = await driver.read(sample_image_uri, timeout=0)
        # Should decode to PNG bytes
        assert content.startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_read_invalid_data_uri_no_prefix(self, driver: DataUriFileDriver) -> None:
        """Test reading data URI without 'data:' prefix raises ValueError."""
        with pytest.raises(ValueError, match="must start with 'data:'"):
            await driver.read("image/png;base64,abc", timeout=0)

    @pytest.mark.asyncio
    async def test_read_invalid_data_uri_no_base64_marker(self, driver: DataUriFileDriver) -> None:
        """Test reading data URI without ';base64,' marker raises ValueError."""
        with pytest.raises(ValueError, match="must contain ';base64,'"):
            await driver.read("data:image/png,abc", timeout=0)

    @pytest.mark.asyncio
    async def test_read_invalid_base64_encoding(self, driver: DataUriFileDriver) -> None:
        """Test reading data URI with invalid base64 encoding raises ValueError."""
        with pytest.raises(ValueError, match="Failed to decode base64"):
            await driver.read("data:image/png;base64,!!!invalid!!!", timeout=0)

    @pytest.mark.asyncio
    async def test_read_ignores_timeout(self, driver: DataUriFileDriver, sample_data_uri: str) -> None:
        """Test that timeout parameter is ignored (no network operation)."""
        # Should work regardless of timeout value
        content = await driver.read(sample_data_uri, timeout=0)
        assert content == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_exists_for_valid_data_uri(self, driver: DataUriFileDriver, sample_data_uri: str) -> None:
        """Test exists returns True for valid data URI."""
        assert await driver.exists(sample_data_uri) is True

    @pytest.mark.asyncio
    async def test_exists_for_invalid_data_uri(self, driver: DataUriFileDriver) -> None:
        """Test exists returns False for invalid data URI."""
        assert await driver.exists("data:image/png,invalid") is False

    def test_get_size_for_valid_data_uri(self, driver: DataUriFileDriver, sample_data_uri: str) -> None:
        """Test get_size returns correct size for valid data URI."""
        size = driver.get_size(sample_data_uri)
        assert size == len(b"Hello, World!")

    def test_get_size_for_image_uri(self, driver: DataUriFileDriver, sample_image_uri: str) -> None:
        """Test get_size returns correct size for image data URI."""
        size = driver.get_size(sample_image_uri)
        # 1x1 PNG is 67 bytes
        assert size > 0

    def test_get_size_for_invalid_data_uri(self, driver: DataUriFileDriver) -> None:
        """Test get_size raises ValueError for invalid data URI."""
        with pytest.raises(ValueError, match="must contain ';base64,'"):
            driver.get_size("data:image/png,invalid")

    @pytest.mark.asyncio
    async def test_read_different_mime_types(self, driver: DataUriFileDriver) -> None:
        """Test reading data URIs with different MIME types."""
        test_cases = [
            ("data:text/plain;base64,", b""),
            ("data:application/json;base64," + base64.b64encode(b'{"key":"value"}').decode(), b'{"key":"value"}'),
            ("data:text/html;base64," + base64.b64encode(b"<html></html>").decode(), b"<html></html>"),
        ]

        for uri, expected_content in test_cases:
            content = await driver.read(uri, timeout=0)
            assert content == expected_content
