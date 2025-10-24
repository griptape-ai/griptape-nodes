import platform
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.os_events import (
    CreateFileRequest,
    CreateFileResultFailure,
    CreateFileResultSuccess,
    ExistingFilePolicy,
    FileIOFailureReason,
    ListDirectoryRequest,
    ListDirectoryResultFailure,
    ListDirectoryResultSuccess,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    RenameFileRequest,
    RenameFileResultFailure,
    RenameFileResultSuccess,
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

# Windows MAX_PATH constant for tests
WINDOWS_MAX_PATH = 260


class TestWriteFileRequest:
    """Test WriteFileRequest with various scenarios."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_write_text_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully writing a text file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        request = WriteFileRequest(file_path=str(file_path), content="Hello, World!")

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        # Compare resolved paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert Path(result.final_file_path).resolve() == file_path.resolve()
        assert result.bytes_written > 0
        assert file_path.read_text() == "Hello, World!"

    def test_write_binary_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully writing a binary file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.bin"
        content = b"\x00\x01\x02\x03"
        request = WriteFileRequest(file_path=str(file_path), content=content)

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        # Compare resolved paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert Path(result.final_file_path).resolve() == file_path.resolve()
        assert result.bytes_written == len(content)
        assert file_path.read_bytes() == content

    def test_write_file_append_mode(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test appending to an existing file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Initial content\n")

        request = WriteFileRequest(file_path=str(file_path), content="Appended content\n", append=True)
        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        assert file_path.read_text() == "Initial content\nAppended content\n"

    def test_write_file_overwrite_policy(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test overwriting an existing file with OVERWRITE policy."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Old content")

        request = WriteFileRequest(
            file_path=str(file_path), content="New content", existing_file_policy=ExistingFilePolicy.OVERWRITE
        )
        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        assert file_path.read_text() == "New content"

    def test_write_file_fail_policy(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test FAIL policy when file exists."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Existing content")

        request = WriteFileRequest(
            file_path=str(file_path), content="New content", existing_file_policy=ExistingFilePolicy.FAIL
        )
        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.POLICY_NO_OVERWRITE
        # Type checker: result_details is always ResultDetails after __post_init__
        assert isinstance(result.result_details, ResultDetails)
        assert "exists" in result.result_details.result_details[0].message.lower()

    def test_write_file_create_new_policy_not_implemented(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW policy returns not implemented error."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        request = WriteFileRequest(
            file_path=str(file_path), content="Content", existing_file_policy=ExistingFilePolicy.CREATE_NEW
        )

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR
        # Type checker: result_details is always ResultDetails after __post_init__
        assert isinstance(result.result_details, ResultDetails)
        assert "not yet implemented" in result.result_details.result_details[0].message.lower()

    def test_write_file_create_parents_true(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test creating parent directories when create_parents=True."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "subdir" / "nested" / "test.txt"
        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=True)

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        assert file_path.exists()
        assert file_path.read_text() == "Content"

    def test_write_file_create_parents_false(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test failure when parent directory missing and create_parents=False."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "nonexistent" / "test.txt"
        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=False)

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS

    def test_write_file_invalid_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test invalid path handling - empty path resolves to directory."""
        os_manager = griptape_nodes.OSManager()
        # Empty string resolves to current directory, which is a directory not a file
        request = WriteFileRequest(file_path="", content="Content")

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        # Empty path resolves to directory, so we get IS_DIRECTORY error
        assert result.failure_reason == FileIOFailureReason.IS_DIRECTORY

    def test_write_file_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test permission denied error."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        request = WriteFileRequest(file_path=str(file_path), content="Content")

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED


class TestReadFileRequest:
    """Test ReadFileRequest with failure_reason support."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_read_text_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully reading a text file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Test content")

        request = ReadFileRequest(file_path=str(file_path))
        result = os_manager.on_read_file_request(request)

        assert isinstance(result, ReadFileResultSuccess)
        assert result.content == "Test content"
        assert result.encoding == "utf-8"

    def test_read_binary_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully reading a binary file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.bin"
        content = b"\x00\x01\x02\x03"
        file_path.write_bytes(content)

        request = ReadFileRequest(file_path=str(file_path))
        result = os_manager.on_read_file_request(request)

        assert isinstance(result, ReadFileResultSuccess)
        # Binary files might be returned as base64 or bytes
        assert result.content is not None

    def test_read_file_not_found(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test reading non-existent file returns FILE_NOT_FOUND."""
        os_manager = griptape_nodes.OSManager()
        request = ReadFileRequest(file_path=str(temp_dir / "nonexistent.txt"))

        result = os_manager.on_read_file_request(request)

        assert isinstance(result, ReadFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND

    def test_read_file_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test reading file without permission."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Content")

        request = ReadFileRequest(file_path=str(file_path))

        # Mock the file operation to raise PermissionError
        with patch.object(Path, "open", side_effect=PermissionError("Permission denied")):
            result = os_manager.on_read_file_request(request)

        assert isinstance(result, ReadFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED

    def test_read_file_invalid_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test reading with invalid path - empty resolves to directory."""
        os_manager = griptape_nodes.OSManager()
        # Empty path resolves to directory, which isn't a file
        request = ReadFileRequest(file_path="")

        result = os_manager.on_read_file_request(request)

        assert isinstance(result, ReadFileResultFailure)
        # FILE_NOT_FOUND is returned when path exists but is not a file
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND


class TestCreateFileRequest:
    """Test CreateFileRequest with failure_reason support."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_create_empty_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test creating an empty file."""
        os_manager = griptape_nodes.OSManager()
        request = CreateFileRequest(path=str(temp_dir / "test.txt"), workspace_only=False)

        result = os_manager.on_create_file_request(request)

        assert isinstance(result, CreateFileResultSuccess)
        assert (temp_dir / "test.txt").exists()

    def test_create_file_with_content(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test creating a file with initial content."""
        os_manager = griptape_nodes.OSManager()
        request = CreateFileRequest(path=str(temp_dir / "test.txt"), content="Initial content", workspace_only=False)

        result = os_manager.on_create_file_request(request)

        assert isinstance(result, CreateFileResultSuccess)
        assert (temp_dir / "test.txt").read_text() == "Initial content"

    def test_create_directory_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test creating a directory."""
        os_manager = griptape_nodes.OSManager()
        request = CreateFileRequest(path=str(temp_dir / "testdir"), is_directory=True, workspace_only=False)

        result = os_manager.on_create_file_request(request)

        assert isinstance(result, CreateFileResultSuccess)
        assert (temp_dir / "testdir").is_dir()

    def test_create_file_already_exists(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test creating file that already exists returns success with warning."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("Existing")

        request = CreateFileRequest(path=str(file_path), workspace_only=False)
        result = os_manager.on_create_file_request(request)

        assert isinstance(result, CreateFileResultSuccess)
        # Should contain warning in result_details
        # Type checker: result_details is always ResultDetails after __post_init__
        assert isinstance(result.result_details, ResultDetails)
        assert "exists" in result.result_details.result_details[0].message.lower()

    def test_create_file_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test permission denied when creating file."""
        os_manager = griptape_nodes.OSManager()
        request = CreateFileRequest(path=str(temp_dir / "test.txt"), workspace_only=False)

        # CreateFile uses Path.touch() for empty files, not Path.open()
        with patch.object(Path, "touch", side_effect=PermissionError("Permission denied")):
            result = os_manager.on_create_file_request(request)

        assert isinstance(result, CreateFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED


class TestRenameFileRequest:
    """Test RenameFileRequest with failure_reason support."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_rename_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully renaming a file."""
        os_manager = griptape_nodes.OSManager()
        old_path = temp_dir / "old.txt"
        new_path = temp_dir / "new.txt"
        old_path.write_text("Content")

        request = RenameFileRequest(old_path=str(old_path), new_path=str(new_path), workspace_only=False)
        result = os_manager.on_rename_file_request(request)

        assert isinstance(result, RenameFileResultSuccess)
        assert not old_path.exists()
        assert new_path.exists()
        assert new_path.read_text() == "Content"

    def test_rename_file_source_not_found(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test renaming non-existent file."""
        os_manager = griptape_nodes.OSManager()
        request = RenameFileRequest(
            old_path=str(temp_dir / "nonexistent.txt"), new_path=str(temp_dir / "new.txt"), workspace_only=False
        )

        result = os_manager.on_rename_file_request(request)

        assert isinstance(result, RenameFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND

    def test_rename_file_destination_exists(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test renaming when destination already exists."""
        os_manager = griptape_nodes.OSManager()
        old_path = temp_dir / "old.txt"
        new_path = temp_dir / "new.txt"
        old_path.write_text("Old content")
        new_path.write_text("New content")

        request = RenameFileRequest(old_path=str(old_path), new_path=str(new_path), workspace_only=False)
        result = os_manager.on_rename_file_request(request)

        assert isinstance(result, RenameFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.INVALID_PATH

    def test_rename_file_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test permission denied when renaming."""
        os_manager = griptape_nodes.OSManager()
        old_path = temp_dir / "old.txt"
        new_path = temp_dir / "new.txt"
        old_path.write_text("Content")

        request = RenameFileRequest(old_path=str(old_path), new_path=str(new_path), workspace_only=False)

        with patch.object(Path, "rename", side_effect=PermissionError("Permission denied")):
            result = os_manager.on_rename_file_request(request)

        assert isinstance(result, RenameFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED


class TestListDirectoryRequest:
    """Test ListDirectoryRequest with failure_reason support."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_list_directory_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully listing a directory."""
        os_manager = griptape_nodes.OSManager()
        # Create some test files
        (temp_dir / "file1.txt").write_text("Content 1")
        (temp_dir / "file2.txt").write_text("Content 2")
        (temp_dir / "subdir").mkdir()

        request = ListDirectoryRequest(directory_path=str(temp_dir), workspace_only=False)
        result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultSuccess)
        assert len(result.entries) == 3  # noqa: PLR2004
        names = {entry.name for entry in result.entries}
        assert names == {"file1.txt", "file2.txt", "subdir"}

    def test_list_directory_hidden_files(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test listing directory with hidden files."""
        os_manager = griptape_nodes.OSManager()
        (temp_dir / "visible.txt").write_text("Content")
        (temp_dir / ".hidden").write_text("Hidden")

        # Without show_hidden
        request = ListDirectoryRequest(directory_path=str(temp_dir), show_hidden=False, workspace_only=False)
        result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultSuccess)
        assert len(result.entries) == 1
        assert result.entries[0].name == "visible.txt"

        # With show_hidden
        request = ListDirectoryRequest(directory_path=str(temp_dir), show_hidden=True, workspace_only=False)
        result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultSuccess)
        assert len(result.entries) == 2  # noqa: PLR2004

    def test_list_directory_not_found(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test listing non-existent directory."""
        os_manager = griptape_nodes.OSManager()
        request = ListDirectoryRequest(directory_path=str(temp_dir / "nonexistent"), workspace_only=False)

        result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultFailure)
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND

    def test_list_directory_not_a_directory(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test listing a file instead of directory."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "file.txt"
        file_path.write_text("Content")

        request = ListDirectoryRequest(directory_path=str(file_path), workspace_only=False)
        result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultFailure)
        assert result.failure_reason == FileIOFailureReason.INVALID_PATH

    def test_list_directory_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test permission denied when listing directory."""
        os_manager = griptape_nodes.OSManager()
        request = ListDirectoryRequest(directory_path=str(temp_dir), workspace_only=False)

        with patch.object(Path, "iterdir", side_effect=PermissionError("Permission denied")):
            result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED


class TestWindowsLongPathHandling:
    r"""Test Windows long path handling with \\?\ prefix."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    @pytest.fixture
    def long_path(self, temp_dir: Path) -> Path:
        """Create a path longer than 260 characters."""
        # Create a path component that when repeated will exceed 260 chars
        long_component = "a" * 50
        path_parts = [temp_dir] + [long_component] * 6  # Will exceed 260 chars
        return Path(*path_parts)

    def test_normalize_path_short_path(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test that short paths are not modified."""
        os_manager = griptape_nodes.OSManager()
        short_path = temp_dir / "short.txt"
        result = os_manager.normalize_path_for_platform(short_path)

        # Should return string without \\?\ prefix
        assert not result.startswith("\\\\?\\")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_normalize_path_long_path_windows(self, griptape_nodes: GriptapeNodes, long_path: Path) -> None:
        r"""Test that long paths on Windows get \\?\ prefix."""
        os_manager = griptape_nodes.OSManager()
        result = os_manager.normalize_path_for_platform(long_path)

        # On Windows, long paths should get the prefix
        if len(str(long_path.resolve())) > WINDOWS_MAX_PATH:
            assert result.startswith("\\\\?\\")

    @pytest.mark.skipif(platform.system() == "Windows", reason="Non-Windows test")
    def test_normalize_path_long_path_non_windows(self, griptape_nodes: GriptapeNodes, long_path: Path) -> None:
        """Test that long paths on non-Windows don't get prefix."""
        os_manager = griptape_nodes.OSManager()
        result = os_manager.normalize_path_for_platform(long_path)

        # On non-Windows, no prefix should be added
        assert not result.startswith("\\\\?\\")

    def test_write_file_with_long_path(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test writing file with long path works correctly."""
        os_manager = griptape_nodes.OSManager()
        # Create a moderately long path (not exceeding OS limits)
        subdir = temp_dir / ("a" * 30) / ("b" * 30) / ("c" * 30)
        file_path = subdir / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=True)
        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        # The returned path should not contain \\?\ prefix
        assert not result.final_file_path.startswith("\\\\?\\")
        # But the file should exist
        assert file_path.exists()


class TestFileIOFailureReasons:
    """Test that all failure reasons are properly set."""

    def test_all_failure_reasons_have_valid_values(self) -> None:
        """Test that all FileIOFailureReason enum values are strings."""
        for reason in FileIOFailureReason:
            assert isinstance(reason.value, str)
            assert len(reason.value) > 0

    def test_failure_reason_uniqueness(self) -> None:
        """Test that all failure reason values are unique."""
        values = [reason.value for reason in FileIOFailureReason]
        assert len(values) == len(set(values))
