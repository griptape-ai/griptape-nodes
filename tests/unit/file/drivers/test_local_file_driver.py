"""Unit tests for LocalFileDriver."""

import platform
from pathlib import Path

import pytest

from griptape_nodes.file.drivers.local_file_driver import LocalFileDriver
from griptape_nodes.file.path_utils import parse_file_uri


class TestLocalFileDriver:
    """Tests for LocalFileDriver class."""

    @pytest.fixture
    def driver(self) -> LocalFileDriver:
        """Create a LocalFileDriver instance."""
        return LocalFileDriver()

    def test_can_handle_always_returns_true(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test that driver always returns True (fallback driver).

        As the fallback driver (priority 100, checked last), LocalFileDriver
        handles any location not matched by a more specific driver.
        """
        absolute_path = tmp_path / "file.txt"
        assert driver.can_handle(str(absolute_path)) is True
        assert driver.can_handle("relative/path/file.txt") is True
        assert driver.can_handle("http://example.com/file.txt") is True
        assert driver.can_handle("data:image/png;base64,abc") is True

    @pytest.mark.asyncio
    async def test_read_existing_file(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test reading an existing file."""
        content = await driver.read(str(temp_file), timeout=10.0)
        assert content == b"test content"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading a non-existent file raises FileNotFoundError."""
        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError) as exc_info:
            await driver.read(str(nonexistent), timeout=10.0)
        assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_directory_raises_error(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading a directory raises IsADirectoryError."""
        with pytest.raises(IsADirectoryError) as exc_info:
            await driver.read(str(tmp_path), timeout=10.0)
        assert "directory" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_with_shell_escapes(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading file with shell escapes in path (macOS Finder)."""
        # Create file with spaces in name
        file_with_spaces = tmp_path / "test file.txt"
        file_with_spaces.write_text("content")

        # Simulate macOS Finder path with shell escapes
        escaped_path = str(file_with_spaces).replace(" ", "\\ ")
        content = await driver.read(escaped_path, timeout=10.0)
        assert content == b"content"

    @pytest.mark.asyncio
    async def test_read_with_tilde_expansion(
        self,
        driver: LocalFileDriver,
        tmp_path: Path,  # noqa: ARG002
    ) -> None:
        """Test reading file with tilde in path."""
        # This test assumes home directory exists
        home_file = Path.home() / ".bashrc"
        if home_file.exists():
            content = await driver.read("~/.bashrc", timeout=10.0)
            assert isinstance(content, bytes)

    @pytest.mark.asyncio
    async def test_exists_for_existing_file(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test exists returns True for existing file."""
        assert await driver.exists(str(temp_file)) is True

    @pytest.mark.asyncio
    async def test_exists_for_nonexistent_file(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test exists returns False for non-existent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        assert await driver.exists(str(nonexistent)) is False

    @pytest.mark.asyncio
    async def test_exists_for_directory(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test exists returns False for directory."""
        assert await driver.exists(str(tmp_path)) is False

    def test_get_size_for_existing_file(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test get_size returns correct size for existing file."""
        size = driver.get_size(str(temp_file))
        assert size == len("test content")

    def test_get_size_for_nonexistent_file(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test get_size raises FileNotFoundError for non-existent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError) as exc_info:
            driver.get_size(str(nonexistent))
        assert "File not found" in str(exc_info.value)

    def test_get_size_for_directory(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test get_size raises IsADirectoryError for directory."""
        with pytest.raises(IsADirectoryError) as exc_info:
            driver.get_size(str(tmp_path))
        assert "directory" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_binary_file(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading binary file content."""
        binary_file = tmp_path / "binary.dat"
        binary_content = bytes([0, 1, 2, 3, 255, 254, 253])
        binary_file.write_bytes(binary_content)

        content = await driver.read(str(binary_file), timeout=10.0)
        assert content == binary_content


class TestLocalFileDriverFileURI:
    """Tests for LocalFileDriver file:// URI support."""

    @pytest.fixture
    def driver(self) -> LocalFileDriver:
        """Create a LocalFileDriver instance."""
        return LocalFileDriver()

    def test_parse_file_uri_unix_absolute(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test parsing Unix absolute path file URI."""
        uri = "file:///path/to/file.txt"
        result = parse_file_uri(uri)
        assert result == "/path/to/file.txt"

    def test_parse_file_uri_localhost(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test parsing file URI with localhost."""
        uri = "file://localhost/path/to/file.txt"
        result = parse_file_uri(uri)
        assert result == "/path/to/file.txt"

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_parse_file_uri_windows_absolute(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test parsing Windows absolute path file URI."""
        uri = "file:///C:/Users/test/file.txt"
        result = parse_file_uri(uri)
        assert result == "C:/Users/test/file.txt"

    def test_parse_file_uri_with_percent_encoding(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test parsing file URI with percent-encoded characters."""
        uri = "file:///path/to/file%20with%20spaces.txt"
        result = parse_file_uri(uri)
        assert result == "/path/to/file with spaces.txt"

    def test_parse_file_uri_rejects_remote_host(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test that file URIs with non-localhost hosts are rejected."""
        uri = "file://remote-server/path/to/file.txt"
        result = parse_file_uri(uri)
        assert result is None

    def test_parse_file_uri_rejects_non_file_scheme(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test that non-file:// URIs are rejected."""
        uri = "http://example.com/file.txt"
        result = parse_file_uri(uri)
        assert result is None

    def test_parse_file_uri_returns_none_for_regular_path(self, driver: LocalFileDriver) -> None:  # noqa: ARG002
        """Test that regular paths (not file:// URIs) return None."""
        result = parse_file_uri("/regular/path/file.txt")
        assert result is None

    def test_can_handle_file_uri_unix(self, driver: LocalFileDriver) -> None:
        """Test that driver handles Unix file:// URIs."""
        uri = "file:///path/to/file.txt"
        assert driver.can_handle(uri) is True

    def test_can_handle_file_uri_localhost(self, driver: LocalFileDriver) -> None:
        """Test that driver handles localhost file:// URIs."""
        uri = "file://localhost/path/to/file.txt"
        assert driver.can_handle(uri) is True

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_can_handle_file_uri_windows(self, driver: LocalFileDriver) -> None:
        """Test that driver handles Windows file:// URIs."""
        uri = "file:///C:/Users/test/file.txt"
        assert driver.can_handle(uri) is True

    def test_can_handle_accepts_remote_file_uri(self, driver: LocalFileDriver) -> None:
        """Test that driver accepts file:// URIs with remote hosts (fallback).

        The driver accepts all locations; invalid URIs fail at read time, not can_handle.
        """
        uri = "file://remote-server/path/to/file.txt"
        assert driver.can_handle(uri) is True

    @pytest.mark.asyncio
    async def test_read_file_uri(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test reading file via file:// URI."""
        # Convert path to file:// URI
        file_uri = temp_file.as_uri()

        content = await driver.read(file_uri, timeout=10.0)
        assert content == b"test content"

    @pytest.mark.asyncio
    async def test_read_file_uri_with_spaces(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading file with spaces in name via file:// URI."""
        file_with_spaces = tmp_path / "test file.txt"
        file_with_spaces.write_text("content with spaces")

        file_uri = file_with_spaces.as_uri()

        content = await driver.read(file_uri, timeout=10.0)
        assert content == b"content with spaces"

    @pytest.mark.asyncio
    async def test_read_file_uri_not_found(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test reading non-existent file via file:// URI raises FileNotFoundError."""
        nonexistent = tmp_path / "nonexistent.txt"
        file_uri = nonexistent.as_uri()

        with pytest.raises(FileNotFoundError) as exc_info:
            await driver.read(file_uri, timeout=10.0)
        assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_invalid_file_uri(self, driver: LocalFileDriver) -> None:
        """Test reading file with invalid file:// URI raises ValueError."""
        invalid_uri = "file://remote-server/path/to/file.txt"

        with pytest.raises(ValueError, match="Invalid file:// URI"):
            await driver.read(invalid_uri, timeout=10.0)

    @pytest.mark.asyncio
    async def test_exists_file_uri(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test exists with file:// URI for existing file."""
        file_uri = temp_file.as_uri()
        assert await driver.exists(file_uri) is True

    @pytest.mark.asyncio
    async def test_exists_file_uri_nonexistent(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test exists with file:// URI for non-existent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        file_uri = nonexistent.as_uri()
        assert await driver.exists(file_uri) is False

    @pytest.mark.asyncio
    async def test_exists_invalid_file_uri(self, driver: LocalFileDriver) -> None:
        """Test exists with invalid file:// URI returns False."""
        invalid_uri = "file://remote-server/path/to/file.txt"
        assert await driver.exists(invalid_uri) is False

    def test_get_size_file_uri(self, driver: LocalFileDriver, temp_file: Path) -> None:
        """Test get_size with file:// URI."""
        file_uri = temp_file.as_uri()
        size = driver.get_size(file_uri)
        assert size == len("test content")

    def test_get_size_file_uri_not_found(self, driver: LocalFileDriver, tmp_path: Path) -> None:
        """Test get_size with file:// URI for non-existent file raises FileNotFoundError."""
        nonexistent = tmp_path / "nonexistent.txt"
        file_uri = nonexistent.as_uri()

        with pytest.raises(FileNotFoundError) as exc_info:
            driver.get_size(file_uri)
        assert "File not found" in str(exc_info.value)

    def test_get_size_invalid_file_uri(self, driver: LocalFileDriver) -> None:
        """Test get_size with invalid file:// URI raises ValueError."""
        invalid_uri = "file://remote-server/path/to/file.txt"

        with pytest.raises(ValueError, match="Invalid file:// URI"):
            driver.get_size(invalid_uri)
