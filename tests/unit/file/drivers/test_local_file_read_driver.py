"""Unit tests for LocalFileReadDriver."""

from pathlib import Path

import pytest

from griptape_nodes.file.drivers.local_file_read_driver import LocalFileReadDriver


class TestLocalFileReadDriver:
    """Tests for LocalFileReadDriver class."""

    @pytest.fixture
    def driver(self) -> LocalFileReadDriver:
        """Create a LocalFileReadDriver instance."""
        return LocalFileReadDriver()

    def test_can_handle_absolute_paths(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test that driver handles absolute paths."""
        # Use a real absolute path that works on all platforms
        absolute_path = tmp_path / "file.txt"
        assert driver.can_handle(str(absolute_path)) is True

    def test_can_handle_rejects_relative_paths(self, driver: LocalFileReadDriver) -> None:
        """Test that driver rejects relative paths."""
        assert driver.can_handle("relative/path/file.txt") is False

    def test_can_handle_rejects_urls(self, driver: LocalFileReadDriver) -> None:
        """Test that driver rejects HTTP URLs."""
        assert driver.can_handle("http://example.com/file.txt") is False
        assert driver.can_handle("https://example.com/file.txt") is False

    def test_can_handle_rejects_data_uris(self, driver: LocalFileReadDriver) -> None:
        """Test that driver rejects data URIs."""
        assert driver.can_handle("data:image/png;base64,abc") is False

    @pytest.mark.asyncio
    async def test_read_existing_file(self, driver: LocalFileReadDriver, temp_file: Path) -> None:
        """Test reading an existing file."""
        content = await driver.read(str(temp_file), timeout=10.0)
        assert content == b"test content"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test reading a non-existent file raises FileNotFoundError."""
        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError) as exc_info:
            await driver.read(str(nonexistent), timeout=10.0)
        assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_directory_raises_error(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test reading a directory raises IsADirectoryError."""
        with pytest.raises(IsADirectoryError) as exc_info:
            await driver.read(str(tmp_path), timeout=10.0)
        assert "directory" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_with_shell_escapes(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
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
        driver: LocalFileReadDriver,
        tmp_path: Path,  # noqa: ARG002
    ) -> None:
        """Test reading file with tilde in path."""
        # This test assumes home directory exists
        home_file = Path.home() / ".bashrc"
        if home_file.exists():
            content = await driver.read("~/.bashrc", timeout=10.0)
            assert isinstance(content, bytes)

    @pytest.mark.asyncio
    async def test_exists_for_existing_file(self, driver: LocalFileReadDriver, temp_file: Path) -> None:
        """Test exists returns True for existing file."""
        assert await driver.exists(str(temp_file)) is True

    @pytest.mark.asyncio
    async def test_exists_for_nonexistent_file(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test exists returns False for non-existent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        assert await driver.exists(str(nonexistent)) is False

    @pytest.mark.asyncio
    async def test_exists_for_directory(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test exists returns False for directory."""
        assert await driver.exists(str(tmp_path)) is False

    def test_get_size_for_existing_file(self, driver: LocalFileReadDriver, temp_file: Path) -> None:
        """Test get_size returns correct size for existing file."""
        size = driver.get_size(str(temp_file))
        assert size == len("test content")

    def test_get_size_for_nonexistent_file(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test get_size raises FileNotFoundError for non-existent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError) as exc_info:
            driver.get_size(str(nonexistent))
        assert "File not found" in str(exc_info.value)

    def test_get_size_for_directory(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test get_size raises IsADirectoryError for directory."""
        with pytest.raises(IsADirectoryError) as exc_info:
            driver.get_size(str(tmp_path))
        assert "directory" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_binary_file(self, driver: LocalFileReadDriver, tmp_path: Path) -> None:
        """Test reading binary file content."""
        binary_file = tmp_path / "binary.dat"
        binary_content = bytes([0, 1, 2, 3, 255, 254, 253])
        binary_file.write_bytes(binary_content)

        content = await driver.read(str(binary_file), timeout=10.0)
        assert content == binary_content
