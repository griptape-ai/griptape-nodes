"""Unit tests for library_utils module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, mock_open, patch

import pygit2
import pytest

from griptape_nodes.utils.git_utils import GitCloneError
from griptape_nodes.utils.library_utils import clone_and_get_library_version, is_monorepo

if TYPE_CHECKING:
    from collections.abc import Generator


class TestIsMonorepo:
    """Test is_monorepo function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_is_monorepo_returns_false_when_not_git_repository(self, temp_dir: Path) -> None:
        """Test that False is returned when path is not a git repository."""
        with patch("griptape_nodes.utils.library_utils.get_git_repository_root") as mock_get_root:
            mock_get_root.return_value = None

            result = is_monorepo(temp_dir)

            assert result is False

    def test_is_monorepo_returns_false_when_only_one_library_json_found(self, temp_dir: Path) -> None:
        """Test that False is returned when only one library JSON file exists."""
        with (
            patch("griptape_nodes.utils.library_utils.get_git_repository_root") as mock_get_root,
            patch("griptape_nodes.utils.library_utils.find_all_files_in_directory") as mock_find,
        ):
            mock_get_root.return_value = temp_dir
            mock_find.return_value = [temp_dir / "griptape_nodes_library.json"]

            result = is_monorepo(temp_dir)

            assert result is False

    def test_is_monorepo_returns_false_when_no_library_json_found(self, temp_dir: Path) -> None:
        """Test that False is returned when no library JSON files exist."""
        with (
            patch("griptape_nodes.utils.library_utils.get_git_repository_root") as mock_get_root,
            patch("griptape_nodes.utils.library_utils.find_all_files_in_directory") as mock_find,
        ):
            mock_get_root.return_value = temp_dir
            mock_find.return_value = []

            result = is_monorepo(temp_dir)

            assert result is False

    def test_is_monorepo_returns_true_when_multiple_library_json_found(self, temp_dir: Path) -> None:
        """Test that True is returned when multiple library JSON files exist."""
        with (
            patch("griptape_nodes.utils.library_utils.get_git_repository_root") as mock_get_root,
            patch("griptape_nodes.utils.library_utils.find_all_files_in_directory") as mock_find,
        ):
            mock_get_root.return_value = temp_dir
            mock_find.return_value = [
                temp_dir / "lib1" / "griptape_nodes_library.json",
                temp_dir / "lib2" / "griptape-nodes-library.json",
            ]

            result = is_monorepo(temp_dir)

            assert result is True

    def test_is_monorepo_searches_with_correct_pattern(self, temp_dir: Path) -> None:
        """Test that correct glob pattern is used for searching."""
        with (
            patch("griptape_nodes.utils.library_utils.get_git_repository_root") as mock_get_root,
            patch("griptape_nodes.utils.library_utils.find_all_files_in_directory") as mock_find,
        ):
            mock_get_root.return_value = temp_dir
            mock_find.return_value = []

            is_monorepo(temp_dir)

            mock_find.assert_called_once_with(temp_dir, "griptape[-_]nodes[-_]library.json")


class TestCloneAndGetLibraryVersion:
    """Test clone_and_get_library_version function."""

    def test_clone_and_get_library_version_converts_ssh_to_https(self) -> None:
        """Test that SSH URLs are converted to HTTPS before cloning."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.git_utils._convert_ssh_to_https") as mock_convert,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = True
            mock_convert.return_value = "https://github.com/user/repo.git"
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"metadata": {"library_version": "1.0.0"}}')
            with patch.object(Path, "open", mock_file):
                clone_and_get_library_version("git@github.com:user/repo.git")

                mock_convert.assert_called_once_with("git@github.com:user/repo.git")

    def test_clone_and_get_library_version_clones_repository_to_temp_dir(self) -> None:
        """Test that repository is cloned to a temporary directory."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"metadata": {"library_version": "1.0.0"}}')
            with patch.object(Path, "open", mock_file):
                clone_and_get_library_version("https://github.com/user/repo.git")

                mock_clone.assert_called_once()
                call_args = mock_clone.call_args
                assert call_args[0][0] == "https://github.com/user/repo.git"
                # Second arg should be a string path (temp directory)
                assert isinstance(call_args[0][1], str)

    def test_clone_and_get_library_version_raises_error_when_clone_fails(self) -> None:
        """Test that GitCloneError is raised when cloning fails."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
        ):
            mock_is_ssh.return_value = False
            mock_clone.side_effect = pygit2.GitError("clone failed")

            with pytest.raises(GitCloneError) as exc_info:
                clone_and_get_library_version("https://github.com/user/repo.git")

            assert "Git error while cloning" in str(exc_info.value)

    def test_clone_and_get_library_version_raises_error_when_clone_returns_none(self) -> None:
        """Test that GitCloneError is raised when clone returns None."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
        ):
            mock_is_ssh.return_value = False
            mock_clone.return_value = None

            with pytest.raises(GitCloneError) as exc_info:
                clone_and_get_library_version("https://github.com/user/repo.git")

            assert "Failed to clone repository" in str(exc_info.value)

    def test_clone_and_get_library_version_raises_error_when_no_library_json_found(self) -> None:
        """Test that GitCloneError is raised when no library JSON file is found."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_find.return_value = None

            with pytest.raises(GitCloneError) as exc_info:
                clone_and_get_library_version("https://github.com/user/repo.git")

            assert "No library JSON file found" in str(exc_info.value)

    def test_clone_and_get_library_version_raises_error_on_invalid_json(self) -> None:
        """Test that GitCloneError is raised when JSON is invalid."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data="invalid json")
            with patch.object(Path, "open", mock_file):
                with pytest.raises(GitCloneError) as exc_info:
                    clone_and_get_library_version("https://github.com/user/repo.git")

                assert "JSON decode error" in str(exc_info.value)

    def test_clone_and_get_library_version_raises_error_when_no_metadata(self) -> None:
        """Test that GitCloneError is raised when no metadata in JSON."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"nodes": []}')
            with patch.object(Path, "open", mock_file):
                with pytest.raises(GitCloneError) as exc_info:
                    clone_and_get_library_version("https://github.com/user/repo.git")

                assert "No metadata found" in str(exc_info.value)

    def test_clone_and_get_library_version_raises_error_when_no_library_version(self) -> None:
        """Test that GitCloneError is raised when no library_version in metadata."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"metadata": {"name": "test"}}')
            with patch.object(Path, "open", mock_file):
                with pytest.raises(GitCloneError) as exc_info:
                    clone_and_get_library_version("https://github.com/user/repo.git")

                assert "No library_version found" in str(exc_info.value)

    def test_clone_and_get_library_version_returns_version_when_successful(self) -> None:
        """Test that library version is returned when all conditions are met."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"metadata": {"library_version": "2.5.1"}}')
            with patch.object(Path, "open", mock_file):
                result = clone_and_get_library_version("https://github.com/user/repo.git")

                assert result == "2.5.1"

    def test_clone_and_get_library_version_searches_recursively_for_library_json(self) -> None:
        """Test that library JSON file is searched recursively."""
        with (
            patch("griptape_nodes.utils.git_utils._is_ssh_url") as mock_is_ssh,
            patch("griptape_nodes.utils.library_utils.pygit2.clone_repository") as mock_clone,
            patch("griptape_nodes.utils.library_utils.find_file_in_directory") as mock_find,
            patch("tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_is_ssh.return_value = False
            mock_repo = Mock()
            mock_clone.return_value = mock_repo
            mock_mkdtemp.return_value = "/tmp/test_temp_dir"  # noqa: S108

            library_json = Path("/tmp/test_temp_dir/subdir/griptape_nodes_library.json")  # noqa: S108
            mock_find.return_value = library_json

            mock_file = mock_open(read_data='{"metadata": {"library_version": "1.0.0"}}')
            with patch.object(Path, "open", mock_file):
                clone_and_get_library_version("https://github.com/user/repo.git")

                mock_find.assert_called_once()
                call_args = mock_find.call_args
                assert call_args[0][1] == "griptape[-_]nodes[-_]library.json"
