"""Unit tests for library_utils module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

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

    def test_clone_and_get_library_version_calls_sparse_checkout(self) -> None:
        """Test that clone_and_get_library_version delegates to sparse_checkout_library_json."""
        with patch("griptape_nodes.utils.library_utils.sparse_checkout_library_json") as mock_sparse:
            mock_sparse.return_value = ("1.0.0", "abc123def456", Path("/tmp/test.json"))  # noqa: S108

            result = clone_and_get_library_version("https://github.com/user/repo.git")

            mock_sparse.assert_called_once_with("https://github.com/user/repo.git")
            assert result == ("1.0.0", "abc123def456")

    def test_clone_and_get_library_version_returns_only_version_and_commit(self) -> None:
        """Test that clone_and_get_library_version returns only version and commit, not path."""
        with patch("griptape_nodes.utils.library_utils.sparse_checkout_library_json") as mock_sparse:
            mock_sparse.return_value = ("2.5.1", "def789ghi012", Path("/tmp/nested/test.json"))  # noqa: S108

            result = clone_and_get_library_version("https://github.com/user/repo.git")

            # Verify returns tuple of (version, commit) only
            assert result == ("2.5.1", "def789ghi012")
            assert isinstance(result, tuple)
            version, commit = result
            assert version == "2.5.1"
            assert commit == "def789ghi012"

    def test_clone_and_get_library_version_propagates_errors(self) -> None:
        """Test that errors from sparse_checkout_library_json are propagated."""
        with patch("griptape_nodes.utils.library_utils.sparse_checkout_library_json") as mock_sparse:
            mock_sparse.side_effect = GitCloneError("sparse checkout failed")

            with pytest.raises(GitCloneError) as exc_info:
                clone_and_get_library_version("https://github.com/user/repo.git")

            assert "sparse checkout failed" in str(exc_info.value)
