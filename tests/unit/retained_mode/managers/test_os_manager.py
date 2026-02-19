import os
import platform
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
import send2trash

from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.os_events import (
    CreateFileRequest,
    CreateFileResultFailure,
    CreateFileResultSuccess,
    DeleteFileRequest,
    DeleteFileResultFailure,
    DeleteFileResultSuccess,
    DeletionBehavior,
    DeletionOutcome,
    ExistingFilePolicy,
    FileIOFailureReason,
    GetFileInfoRequest,
    GetFileInfoResultFailure,
    GetFileInfoResultSuccess,
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
from griptape_nodes.retained_mode.managers.os_manager import OSManager, WindowsSpecialFolderError

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

    def test_write_file_invalid_path(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test invalid path handling - attempting to write to a directory."""
        os_manager = griptape_nodes.OSManager()
        # Create a directory and try to write to it as if it were a file
        dir_path = temp_dir / "test_directory"
        dir_path.mkdir()

        request = WriteFileRequest(file_path=str(dir_path), content="Content")

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        # Attempting to write to a directory path should fail
        # Windows raises PermissionError, Unix/macOS raises IsADirectoryError
        if platform.system() == "Windows":
            assert result.failure_reason in (
                FileIOFailureReason.IS_DIRECTORY,
                FileIOFailureReason.PERMISSION_DENIED,
            )
        else:
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
        file_path = temp_dir / "test.txt"
        file_path.write_text("Test content")

        request = ReadFileRequest(file_path=str(file_path))
        result = griptape_nodes.handle_request(request)

        assert isinstance(result, ReadFileResultSuccess)
        assert result.content == "Test content"
        assert result.encoding == "utf-8"

    def test_read_binary_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully reading a binary file."""
        file_path = temp_dir / "test.bin"
        content = b"\x00\x01\x02\x03"
        file_path.write_bytes(content)

        request = ReadFileRequest(file_path=str(file_path))
        result = griptape_nodes.handle_request(request)

        assert isinstance(result, ReadFileResultSuccess)
        # Binary files might be returned as base64 or bytes
        assert result.content is not None

    def test_read_file_not_found(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test reading non-existent file returns FILE_NOT_FOUND."""
        request = ReadFileRequest(file_path=str(temp_dir / "nonexistent.txt"))

        result = griptape_nodes.handle_request(request)

        assert isinstance(result, ReadFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND

    def test_read_file_permission_denied(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test reading file without permission."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("Content")

        request = ReadFileRequest(file_path=str(file_path))

        # Mock the file operation to raise PermissionError
        with patch.object(Path, "open", side_effect=PermissionError("Permission denied")):
            result = griptape_nodes.handle_request(request)

        assert isinstance(result, ReadFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED

    def test_read_file_invalid_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test reading with invalid path - empty path."""
        # Empty path is invalid
        request = ReadFileRequest(file_path="")

        result = griptape_nodes.handle_request(request)

        assert isinstance(result, ReadFileResultFailure)
        # INVALID_PATH is returned for empty path
        assert result.failure_reason == FileIOFailureReason.INVALID_PATH


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

        # Mock os.scandir() instead of Path.iterdir() since we now use os.scandir() for better performance
        # os.scandir() is used as a context manager, so we need to make it raise PermissionError when called
        with patch(
            "griptape_nodes.retained_mode.managers.os_manager.os.scandir",
            side_effect=PermissionError("Permission denied"),
        ):
            result = os_manager.on_list_directory_request(request)

        assert isinstance(result, ListDirectoryResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED


class TestNormalizePathPartsForSpecialFolder:
    """Test normalize_path_parts_for_special_folder helper."""

    def test_tilde_single_part(self) -> None:
        """~/Downloads -> ['downloads']."""
        result = OSManager.normalize_path_parts_for_special_folder("~/Downloads")
        assert result == ["downloads"]

    def test_tilde_with_slash_single_part(self) -> None:
        """~/Desktop -> ['desktop']."""
        result = OSManager.normalize_path_parts_for_special_folder("~/Desktop")
        assert result == ["desktop"]

    def test_tilde_multiple_parts(self) -> None:
        """~/Desktop/subfolder -> ['desktop', 'subfolder']."""
        result = OSManager.normalize_path_parts_for_special_folder("~/Desktop/subfolder")
        assert result == ["desktop", "subfolder"]

    def test_tilde_only(self) -> None:
        """~ -> [] (no path parts after stripping)."""
        result = OSManager.normalize_path_parts_for_special_folder("~")
        assert result == []

    def test_backslash_normalized_to_slash(self) -> None:
        r"""~\Downloads -> ['downloads']."""
        result = OSManager.normalize_path_parts_for_special_folder("~\\Downloads")
        assert result == ["downloads"]

    def test_empty_string(self) -> None:
        """Empty string -> []."""
        result = OSManager.normalize_path_parts_for_special_folder("")
        assert result == []

    def test_parts_lowercased(self) -> None:
        """Path parts are lowercased."""
        result = OSManager.normalize_path_parts_for_special_folder("~/DOCUMENTS/SubDir")
        assert result == ["documents", "subdir"]

    def test_userprofile_desktop_normalizes_to_desktop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        r"""%UserProfile%\Desktop -> ['desktop']; expandvars can return backslashes on Windows."""
        monkeypatch.setenv("USERPROFILE", "C:\\Users\\jason")

        def expandvars_windows_style(path: str) -> str:
            if "%UserProfile%" in path or "%USERPROFILE%" in path:
                return path.replace("%UserProfile%", "C:\\Users\\jason").replace("%USERPROFILE%", "C:\\Users\\jason")
            return os.path.expandvars(path)

        with patch("griptape_nodes.retained_mode.managers.os_manager.os.path.expandvars", expandvars_windows_style):
            result = OSManager.normalize_path_parts_for_special_folder("%UserProfile%/Desktop")
        assert result == ["desktop"]

    def test_userprofile_downloads_with_subdir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        r"""%UserProfile%\Downloads\sub -> ['downloads', 'sub']."""
        monkeypatch.setenv("USERPROFILE", "C:\\Users\\jason")

        def expandvars_windows_style(path: str) -> str:
            if "%UserProfile%" in path or "%USERPROFILE%" in path:
                return path.replace("%UserProfile%", "C:\\Users\\jason").replace("%USERPROFILE%", "C:\\Users\\jason")
            return os.path.expandvars(path)

        with patch("griptape_nodes.retained_mode.managers.os_manager.os.path.expandvars", expandvars_windows_style):
            result = OSManager.normalize_path_parts_for_special_folder("%UserProfile%/Downloads/sub")
        assert result == ["downloads", "sub"]


class TestTryResolveWindowsSpecialFolder:
    """Test try_resolve_windows_special_folder helper."""

    def test_unknown_folder_returns_none(self, griptape_nodes: GriptapeNodes) -> None:
        """Unknown first part returns None."""
        os_manager = griptape_nodes.OSManager()
        result = os_manager.try_resolve_windows_special_folder(["unknown", "sub"])
        assert result is None

    def test_empty_parts_returns_none(self, griptape_nodes: GriptapeNodes) -> None:
        """Empty parts returns None."""
        os_manager = griptape_nodes.OSManager()
        result = os_manager.try_resolve_windows_special_folder([])
        assert result is None

    def test_downloads_resolved_returns_path_and_empty_remaining(self, griptape_nodes: GriptapeNodes) -> None:
        """Known folder with no remaining parts."""
        os_manager = griptape_nodes.OSManager()
        mock_path = Path("/mock/Downloads")

        def mock_get(csidl: int) -> Path:
            assert csidl == OSManager.WINDOWS_CSIDL_MAP["downloads"]
            return mock_path

        with patch.object(os_manager, "_get_windows_special_folder_path", side_effect=mock_get):
            result = os_manager.try_resolve_windows_special_folder(["downloads"])
        assert result is not None
        assert result.special_path == mock_path
        assert result.remaining_parts == []

    def test_desktop_with_remaining_parts(self, griptape_nodes: GriptapeNodes) -> None:
        """Known folder with remaining parts."""
        os_manager = griptape_nodes.OSManager()
        mock_path = Path("/mock/Desktop")

        def mock_get(csidl: int) -> Path:
            assert csidl == OSManager.WINDOWS_CSIDL_MAP["desktop"]
            return mock_path

        with patch.object(os_manager, "_get_windows_special_folder_path", side_effect=mock_get):
            result = os_manager.try_resolve_windows_special_folder(["desktop", "sub", "file.txt"])
        assert result is not None
        assert result.special_path == mock_path
        assert result.remaining_parts == ["sub", "file.txt"]

    def test_get_folder_raises_returns_none(self, griptape_nodes: GriptapeNodes) -> None:
        """When _get_windows_special_folder_path raises WindowsSpecialFolderError, result is None."""
        os_manager = griptape_nodes.OSManager()
        with patch.object(
            os_manager, "_get_windows_special_folder_path", side_effect=WindowsSpecialFolderError("mock")
        ):
            result = os_manager.try_resolve_windows_special_folder(["downloads"])
        assert result is None


class TestExpandPath:
    """Test OSManager._expand_path integration."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Set workspace to temp_dir for tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_expand_path_relative_resolved_against_cwd(
        self,
        griptape_nodes: GriptapeNodes,
        temp_dir: Path,  # noqa: ARG002
    ) -> None:
        """Relative path is resolved against current working directory."""
        os_manager = griptape_nodes.OSManager()
        result = os_manager._expand_path("subdir")
        # resolve_path_safely resolves relative paths against Path.cwd()
        assert result.is_absolute()
        assert result.name == "subdir"

    def test_expand_path_expands_vars_and_tilde(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Expandvars and expanduser are applied when not a Windows special folder."""
        os_manager = griptape_nodes.OSManager()
        # Use a path that won't match Windows special folder logic on this platform
        result = os_manager._expand_path(str(temp_dir))
        assert result == temp_dir or result.resolve() == temp_dir.resolve()

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific special folder test")
    def test_expand_path_windows_special_folder_mocked(
        self,
        griptape_nodes: GriptapeNodes,
        temp_dir: Path,  # noqa: ARG002
    ) -> None:
        """On Windows, special folder is resolved via Shell API when path is ~/Downloads."""
        os_manager = griptape_nodes.OSManager()
        mock_downloads = Path("C:/mock/Downloads")

        with patch.object(os_manager, "_get_windows_special_folder_path", return_value=mock_downloads) as mock_get:
            result = os_manager._expand_path("~/Downloads")
            mock_get.assert_called_once()
            assert result == os_manager.resolve_path_safely(mock_downloads)

    def test_expand_path_non_windows_uses_expanduser(
        self,
        griptape_nodes: GriptapeNodes,
        temp_dir: Path,  # noqa: ARG002
    ) -> None:
        """On non-Windows, ~/path uses expanduser (no special folder logic)."""
        if platform.system() == "Windows":
            pytest.skip("Non-Windows test")
        os_manager = griptape_nodes.OSManager()
        result = os_manager._expand_path("~/Downloads")
        expected = os_manager.resolve_path_safely(Path.home() / "Downloads")
        assert result == expected


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
        if len(str(long_path.resolve())) >= WINDOWS_MAX_PATH:
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


class TestDeleteFileRequest:
    """Test DeleteFileRequest with various scenarios."""

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

    @pytest.mark.asyncio
    async def test_delete_file_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully deleting a file."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")
        request = DeleteFileRequest(path=str(file_path), workspace_only=False)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        # Compare resolved paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert Path(result.deleted_path).resolve() == file_path.resolve()
        assert result.was_directory is False
        assert len(result.deleted_paths) == 1
        assert Path(result.deleted_paths[0]).resolve() == file_path.resolve()
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_empty_directory(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test deleting an empty directory."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        request = DeleteFileRequest(path=str(dir_path), workspace_only=False)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.was_directory is True
        assert len(result.deleted_paths) >= 1
        assert str(dir_path) in result.deleted_paths or str(dir_path.resolve()) in result.deleted_paths
        assert not dir_path.exists()

    @pytest.mark.asyncio
    async def test_delete_directory_with_contents(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test deleting a directory with contents."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")
        (dir_path / "file2.txt").write_text("content2")
        subdir = dir_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        request = DeleteFileRequest(path=str(dir_path), workspace_only=False)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.was_directory is True
        expected_items = 4  # dir + 2 files + subdir + 1 file
        assert len(result.deleted_paths) >= expected_items
        # Verify that all expected paths are in the deleted_paths list
        assert any(str(dir_path / "file1.txt") in path for path in result.deleted_paths)
        assert any(str(dir_path / "file2.txt") in path for path in result.deleted_paths)
        assert any(str(subdir / "file3.txt") in path for path in result.deleted_paths)
        assert not dir_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file_fails(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test that deleting a nonexistent file fails."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "nonexistent.txt"
        request = DeleteFileRequest(path=str(file_path), workspace_only=False)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.FILE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_invalid_path_fails(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that deleting with neither path nor file_entry fails."""
        os_manager = griptape_nodes.OSManager()
        request = DeleteFileRequest(path=None, file_entry=None)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.INVALID_PATH

    @pytest.mark.asyncio
    async def test_delete_with_permission_error(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test that permission errors are properly handled."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        with patch.object(Path, "unlink", side_effect=PermissionError("Access denied")):
            request = DeleteFileRequest(
                path=str(file_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.PERMANENTLY_DELETE,
            )
            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_delete_file_behavior_permanently_delete(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test default PERMANENTLY_DELETE behavior for files."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")
        request = DeleteFileRequest(
            path=str(file_path),
            workspace_only=False,
            deletion_behavior=DeletionBehavior.PERMANENTLY_DELETE,
        )

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.PERMANENTLY_DELETED
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_directory_behavior_permanently_delete(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test default PERMANENTLY_DELETE behavior for directories."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")
        request = DeleteFileRequest(
            path=str(dir_path),
            workspace_only=False,
            deletion_behavior=DeletionBehavior.PERMANENTLY_DELETE,
        )

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.PERMANENTLY_DELETED
        assert result.was_directory is True
        assert not dir_path.exists()

    @pytest.mark.asyncio
    async def test_delete_file_behavior_recycle_bin_only_success(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test RECYCLE_BIN_ONLY behavior successfully sends file to recycle bin."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.return_value = None
            request = DeleteFileRequest(
                path=str(file_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.RECYCLE_BIN_ONLY,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.SENT_TO_RECYCLE_BIN
        mock_send2trash.send2trash.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_directory_behavior_recycle_bin_only_success(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test RECYCLE_BIN_ONLY behavior successfully sends directory to recycle bin."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.return_value = None
            request = DeleteFileRequest(
                path=str(dir_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.RECYCLE_BIN_ONLY,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.SENT_TO_RECYCLE_BIN
        assert result.was_directory is True
        mock_send2trash.send2trash.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_behavior_recycle_bin_only_failure(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test RECYCLE_BIN_ONLY behavior returns failure when recycle bin unavailable."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.side_effect = OSError("I/O error")
            request = DeleteFileRequest(
                path=str(file_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.RECYCLE_BIN_ONLY,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR

    @pytest.mark.asyncio
    async def test_delete_directory_behavior_recycle_bin_only_failure(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test RECYCLE_BIN_ONLY behavior returns failure for directories when I/O error occurs."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.side_effect = OSError("I/O error")
            request = DeleteFileRequest(
                path=str(dir_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.RECYCLE_BIN_ONLY,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR

    @pytest.mark.asyncio
    async def test_delete_file_behavior_prefer_recycle_bin_uses_trash(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test PREFER_RECYCLE_BIN behavior uses recycle bin when available."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.return_value = None
            request = DeleteFileRequest(
                path=str(file_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.PREFER_RECYCLE_BIN,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.SENT_TO_RECYCLE_BIN
        mock_send2trash.send2trash.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_directory_behavior_prefer_recycle_bin_uses_trash(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test PREFER_RECYCLE_BIN behavior uses recycle bin for directories when available."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.return_value = None
            request = DeleteFileRequest(
                path=str(dir_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.PREFER_RECYCLE_BIN,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.SENT_TO_RECYCLE_BIN
        assert result.was_directory is True
        mock_send2trash.send2trash.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_behavior_prefer_recycle_bin_falls_back(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test PREFER_RECYCLE_BIN behavior falls back to permanent deletion when trash fails."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.side_effect = OSError("Recycle bin unavailable")
            request = DeleteFileRequest(
                path=str(file_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.PREFER_RECYCLE_BIN,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.PERMANENTLY_DELETED
        assert not file_path.exists()
        # Verify result_details is WARNING level
        assert isinstance(result.result_details, ResultDetails)

    @pytest.mark.asyncio
    async def test_delete_directory_behavior_prefer_recycle_bin_falls_back(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test PREFER_RECYCLE_BIN behavior falls back to permanent deletion for directories when trash fails."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("content1")

        with patch("griptape_nodes.retained_mode.managers.os_manager.send2trash") as mock_send2trash:
            mock_send2trash.TrashPermissionError = send2trash.TrashPermissionError
            mock_send2trash.send2trash.side_effect = OSError("Recycle bin unavailable")
            request = DeleteFileRequest(
                path=str(dir_path),
                workspace_only=False,
                deletion_behavior=DeletionBehavior.PREFER_RECYCLE_BIN,
            )

            result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.PERMANENTLY_DELETED
        assert result.was_directory is True
        assert not dir_path.exists()
        # Verify result_details is WARNING level
        assert isinstance(result.result_details, ResultDetails)

    @pytest.mark.asyncio
    async def test_delete_outcome_default_is_sent_to_recycle_bin(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test that default deletion (no behavior specified) reports SENT_TO_RECYCLE_BIN outcome."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")
        request = DeleteFileRequest(path=str(file_path), workspace_only=False)

        result = await os_manager.on_delete_file_request(request)

        assert isinstance(result, DeleteFileResultSuccess)
        assert result.outcome == DeletionOutcome.SENT_TO_RECYCLE_BIN


class TestGetFileInfoRequest:
    """Test GetFileInfoRequest with various scenarios."""

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

    def test_get_file_info_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully getting file info."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")
        request = GetFileInfoRequest(path=str(file_path), workspace_only=False)

        result = os_manager.on_get_file_info_request(request)

        assert isinstance(result, GetFileInfoResultSuccess)
        assert result.file_entry is not None
        assert result.file_entry.is_dir is False
        assert result.file_entry.name == "test.txt"
        assert result.file_entry.size > 0
        assert result.file_entry.mime_type is not None

    def test_get_directory_info_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test successfully getting directory info."""
        os_manager = griptape_nodes.OSManager()
        dir_path = temp_dir / "testdir"
        dir_path.mkdir()
        request = GetFileInfoRequest(path=str(dir_path), workspace_only=False)

        result = os_manager.on_get_file_info_request(request)

        assert isinstance(result, GetFileInfoResultSuccess)
        assert result.file_entry is not None
        assert result.file_entry.is_dir is True
        assert result.file_entry.name == "testdir"
        assert result.file_entry.mime_type is None

    def test_get_file_info_nonexistent_returns_none(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test that getting info for nonexistent path returns success with file_entry=None."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "nonexistent.txt"
        request = GetFileInfoRequest(path=str(file_path), workspace_only=False)

        result = os_manager.on_get_file_info_request(request)

        assert isinstance(result, GetFileInfoResultSuccess)
        assert result.file_entry is None

    def test_get_file_info_empty_path_fails(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that empty path fails."""
        os_manager = griptape_nodes.OSManager()
        request = GetFileInfoRequest(path="", workspace_only=False)

        result = os_manager.on_get_file_info_request(request)

        assert isinstance(result, GetFileInfoResultFailure)
        assert result.failure_reason == FileIOFailureReason.INVALID_PATH


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


class TestCreateNewFilePolicy:
    """Test CREATE_NEW file policy with auto-incrementing filenames."""

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

    def test_create_new_first_file(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW policy creates file with requested name if available."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"
        request = WriteFileRequest(
            file_path=str(file_path),
            content="First file",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        # First file should use requested name (test.txt) since it's available
        expected_path = temp_dir / "test.txt"
        assert Path(result.final_file_path).resolve() == expected_path.resolve()
        assert expected_path.read_text() == "First file"

    def test_create_new_increments_suffix(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW policy increments suffix for subsequent files."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "output.txt"

        # Create first file (gets output.txt since it's available)
        request1 = WriteFileRequest(
            file_path=str(file_path),
            content="File 1",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result1 = os_manager.on_write_file_request(request1)
        assert isinstance(result1, WriteFileResultSuccess)
        assert (temp_dir / "output.txt").exists()

        # Create second file (gets output_1.txt since output.txt now exists)
        request2 = WriteFileRequest(
            file_path=str(file_path),
            content="File 2",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result2 = os_manager.on_write_file_request(request2)
        assert isinstance(result2, WriteFileResultSuccess)
        assert (temp_dir / "output_1.txt").exists()

        # Create third file (gets output_2.txt)
        request3 = WriteFileRequest(
            file_path=str(file_path),
            content="File 3",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result3 = os_manager.on_write_file_request(request3)
        assert isinstance(result3, WriteFileResultSuccess)
        assert (temp_dir / "output_2.txt").exists()

    def test_create_new_fills_gaps(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW policy fills gaps in sequence."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "render.png"

        # Create render.png and files with gaps manually
        (temp_dir / "render.png").write_text("Original")
        (temp_dir / "render_1.png").write_text("File 1")
        (temp_dir / "render_5.png").write_text("File 5")

        # CREATE_NEW should fill gap at _2
        request = WriteFileRequest(
            file_path=str(file_path),
            content="File 2",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result = os_manager.on_write_file_request(request)
        assert isinstance(result, WriteFileResultSuccess)
        expected_path = temp_dir / "render_2.png"
        assert Path(result.final_file_path).resolve() == expected_path.resolve()

    def test_create_new_with_fully_resolved_macro_should_use_suffix_injection(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test CREATE_NEW policy with fully-resolved MacroPath falls back to suffix injection.

        When a MacroPath has all variables resolved and no index variable, the CREATE_NEW
        policy should fall back to parsing the filename and adding _N suffix. Currently
        this fails with "no index variable found".
        """
        from griptape_nodes.common.macro_parser import ParsedMacro
        from griptape_nodes.retained_mode.events.project_events import MacroPath

        os_manager = griptape_nodes.OSManager()

        # Create first file manually
        first_file = temp_dir / "render.png"
        first_file.write_text("Original")

        # Use MacroPath with all variables resolved (no index variable)
        macro_path = MacroPath(
            parsed_macro=ParsedMacro(f"{temp_dir}/render.png"),
            variables={},  # No variables to resolve
        )

        # This should fall back to suffix injection and create render_1.png
        request = WriteFileRequest(
            file_path=macro_path,
            content="Second file",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        result = os_manager.on_write_file_request(request)

        # EXPECTED: Should succeed and create render_1.png
        # ACTUAL: Currently fails with WriteFileResultFailure
        assert isinstance(result, WriteFileResultSuccess)
        expected_path = temp_dir / "render_1.png"
        assert Path(result.final_file_path).resolve() == expected_path.resolve()
        assert expected_path.read_text() == "Second file"


class TestDecomposeSourcePath:
    """Test OSManager.decompose_source_path() for preview path generation.

    These tests verify the path decomposition logic outlined in the preview path
    generation plan, covering all 15 scenarios including workspace files, external
    files, Windows drives, macOS volumes, Linux mounts, and UNC paths.
    """

    def test_workspace_file_root_level(self) -> None:
        """Test workspace file at root level (no subdirectories)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Users/james/workspace/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path is None
        assert result.source_file_name == "photo.png"

    def test_workspace_file_single_subdir(self) -> None:
        """Test workspace file in single subdirectory (Scenario 1)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Users/james/workspace/images/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "images"
        assert result.source_file_name == "photo.png"

    def test_workspace_file_nested_subdirs(self) -> None:
        """Test workspace file in nested subdirectories (Scenario 2)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Users/james/workspace/images/subdir/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "images/subdir"
        assert result.source_file_name == "photo.png"

    def test_workspace_file_outputs_dir(self) -> None:
        """Test workspace file in outputs directory (Scenario 3)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Users/james/workspace/outputs/render.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "outputs"
        assert result.source_file_name == "render.png"

    def test_unix_absolute_path_single_subdir(self) -> None:
        """Test Unix absolute path with single subdirectory (Scenario 4)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/tmp/external.png")  # noqa: S108

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "tmp"
        assert result.source_file_name == "external.png"

    def test_unix_absolute_path_nested_subdirs(self) -> None:
        """Test Unix absolute path with nested subdirectories (Scenario 5)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/tmp/project/images/photo.png")  # noqa: S108

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "tmp/project/images"
        assert result.source_file_name == "photo.png"

    def test_unix_root_level_file(self) -> None:
        """Test Unix root-level file (Scenario 6)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/external.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path is None
        assert result.source_file_name == "external.png"

    def test_windows_drive_c(self) -> None:
        """Test Windows C: drive path (Scenario 11)."""
        workspace = Path("/Users/james/workspace")
        # Simulate Windows path
        source = Path("C:/temp/external.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "C"
        assert result.source_relative_path == "temp"
        assert result.source_file_name == "external.png"

    def test_windows_drive_q(self) -> None:
        """Test Windows Q: drive path (Scenario 12)."""
        workspace = Path("/Users/james/workspace")
        source = Path("Q:/temp/external.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "Q"
        assert result.source_relative_path == "temp"
        assert result.source_file_name == "external.png"

    def test_windows_drive_case_insensitive(self) -> None:
        """Test Windows drive letter is case-insensitive."""
        workspace = Path("/Users/james/workspace")
        source_lower = Path("c:/temp/file.txt")
        source_upper = Path("C:/temp/file.txt")

        result_lower = OSManager.decompose_source_path(source_lower, workspace)
        result_upper = OSManager.decompose_source_path(source_upper, workspace)

        # Both should normalize to uppercase
        assert result_lower.drive_volume_mount == "C"
        assert result_upper.drive_volume_mount == "C"

    def test_macos_volume_basic(self) -> None:
        """Test macOS external volume (Scenario 13)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Volumes/Backup/files/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "Volumes/Backup"
        assert result.source_relative_path == "files"
        assert result.source_file_name == "photo.png"

    def test_macos_volume_root_level(self) -> None:
        """Test macOS volume with file at root."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Volumes/Backup/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "Volumes/Backup"
        assert result.source_relative_path is None
        assert result.source_file_name == "photo.png"

    def test_macos_volume_nested_subdirs(self) -> None:
        """Test macOS volume with nested subdirectories."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Volumes/Backup/projects/2024/images/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "Volumes/Backup"
        assert result.source_relative_path == "projects/2024/images"
        assert result.source_file_name == "photo.png"

    def test_linux_mount_mnt(self) -> None:
        """Test Linux /mnt/ mount (Scenario 14)."""
        workspace = Path("/Users/james/workspace")
        source = Path("/mnt/backup/files/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "mnt/backup"
        assert result.source_relative_path == "files"
        assert result.source_file_name == "photo.png"

    def test_linux_mount_media(self) -> None:
        """Test Linux /media/ mount."""
        workspace = Path("/Users/james/workspace")
        source = Path("/media/usb/documents/file.pdf")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "media/usb"
        assert result.source_relative_path == "documents"
        assert result.source_file_name == "file.pdf"

    def test_linux_mount_root_level(self) -> None:
        """Test Linux mount with file at root."""
        workspace = Path("/Users/james/workspace")
        source = Path("/mnt/backup/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "mnt/backup"
        assert result.source_relative_path is None
        assert result.source_file_name == "photo.png"

    def test_windows_unc_path_root_level(self) -> None:
        """Test Windows UNC path with file at share root (Scenario 15)."""
        workspace = Path("/Users/james/workspace")
        # UNC paths start with //
        source = Path("//server/share/photo.png")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "server/share"
        assert result.source_relative_path is None
        assert result.source_file_name == "photo.png"

    def test_windows_unc_path_with_subdirs(self) -> None:
        """Test Windows UNC path with subdirectories."""
        workspace = Path("/Users/james/workspace")
        source = Path("//server/share/documents/2024/report.pdf")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "server/share"
        assert result.source_relative_path == "documents/2024"
        assert result.source_file_name == "report.pdf"

    def test_windows_long_path_prefix_stripped(self) -> None:
        r"""Test Windows long path prefix (\\?\) is stripped before decomposition."""
        workspace = Path("/Users/james/workspace")
        # Simulate long path with \\?\ prefix
        source = Path("//?/C:/very/long/path/file.txt")

        result = OSManager.decompose_source_path(source, workspace)

        # Should strip prefix and decompose as normal C: path
        assert result.drive_volume_mount == "C"
        assert result.source_relative_path == "very/long/path"
        assert result.source_file_name == "file.txt"

    def test_windows_long_unc_prefix_stripped(self) -> None:
        r"""Test Windows long UNC prefix (\\?\UNC\) is stripped."""
        workspace = Path("/Users/james/workspace")
        # Simulate long UNC path with \\?\UNC\ prefix
        source = Path("//?/UNC/server/share/file.txt")

        result = OSManager.decompose_source_path(source, workspace)

        # Should strip prefix and decompose as normal UNC path
        assert result.drive_volume_mount == "server/share"
        assert result.source_relative_path is None
        assert result.source_file_name == "file.txt"

    def test_complex_filename_preserved(self) -> None:
        """Test that complex filenames with multiple extensions are preserved."""
        workspace = Path("/Users/james/workspace")
        source = Path("/Users/james/workspace/output/archive.tar.gz")

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount is None
        assert result.source_relative_path == "output"
        assert result.source_file_name == "archive.tar.gz"

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific path handling test")
    def test_backslashes_normalized(self) -> None:
        r"""Test that backslashes in paths are normalized to forward slashes."""
        workspace = Path("/Users/james/workspace")
        # Path with backslashes
        source_str = "C:\\Users\\james\\Documents\\file.txt"
        source = Path(source_str)

        result = OSManager.decompose_source_path(source, workspace)

        assert result.drive_volume_mount == "C"
        assert result.source_relative_path == "Users/james/Documents"
        assert result.source_file_name == "file.txt"
