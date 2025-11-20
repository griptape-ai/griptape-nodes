"""Unit tests for file_utils module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.utils.file_utils import find_all_files_in_directory, find_file_in_directory

if TYPE_CHECKING:
    from collections.abc import Generator


class TestFindFileInDirectory:
    """Test find_file_in_directory function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_find_file_when_directory_does_not_exist(self) -> None:
        """Test that None is returned when directory doesn't exist."""
        non_existent = Path("/non/existent/directory")
        result = find_file_in_directory(non_existent, "*.json")

        assert result is None

    def test_find_file_when_path_is_not_directory(self, temp_dir: Path) -> None:
        """Test that None is returned when path is a file, not a directory."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        result = find_file_in_directory(test_file, "*.json")

        assert result is None

    def test_find_file_when_no_files_match_pattern(self, temp_dir: Path) -> None:
        """Test that None is returned when no files match the pattern."""
        (temp_dir / "test.txt").write_text("content")
        (temp_dir / "another.py").write_text("content")

        result = find_file_in_directory(temp_dir, "*.json")

        assert result is None

    def test_find_file_returns_first_match_in_root_directory(self, temp_dir: Path) -> None:
        """Test that first matching file is returned from root directory."""
        expected_file = temp_dir / "config.json"
        expected_file.write_text("{}")

        result = find_file_in_directory(temp_dir, "config.json")

        assert result == expected_file

    def test_find_file_searches_subdirectories_recursively(self, temp_dir: Path) -> None:
        """Test that function searches subdirectories recursively."""
        subdir = temp_dir / "subdir" / "nested"
        subdir.mkdir(parents=True)
        expected_file = subdir / "config.json"
        expected_file.write_text("{}")

        result = find_file_in_directory(temp_dir, "config.json")

        assert result == expected_file

    def test_find_file_matches_glob_pattern(self, temp_dir: Path) -> None:
        """Test that function matches files using glob patterns."""
        expected_file = temp_dir / "my_library.json"
        expected_file.write_text("{}")
        (temp_dir / "other.txt").write_text("content")

        result = find_file_in_directory(temp_dir, "*library*.json")

        assert result == expected_file

    def test_find_file_logs_warning_when_multiple_matches_found(self, temp_dir: Path) -> None:
        """Test that warning is logged when multiple files match pattern."""
        file1 = temp_dir / "config1.json"
        file2 = temp_dir / "config2.json"
        file1.write_text("{}")
        file2.write_text("{}")

        with patch("griptape_nodes.utils.file_utils.logger") as mock_logger:
            result = find_file_in_directory(temp_dir, "*.json")

            assert result in [file1, file2]
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "multiple files" in warning_call.lower()

    def test_find_file_returns_first_match_when_multiple_found(self, temp_dir: Path) -> None:
        """Test that first match is returned when multiple files match."""
        file1 = temp_dir / "a_config.json"
        file2 = temp_dir / "b_config.json"
        file1.write_text("{}")
        file2.write_text("{}")

        result = find_file_in_directory(temp_dir, "*.json")

        # Should return one of them (first found by os.walk)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"

    def test_find_file_matches_character_class_pattern_underscore(self, temp_dir: Path) -> None:
        """Test that character class pattern matches underscore version."""
        expected_file = temp_dir / "griptape_nodes_library.json"
        expected_file.write_text("{}")

        result = find_file_in_directory(temp_dir, "griptape[-_]nodes[-_]library.json")

        assert result == expected_file

    def test_find_file_matches_character_class_pattern_hyphen(self, temp_dir: Path) -> None:
        """Test that character class pattern matches hyphen version."""
        expected_file = temp_dir / "griptape-nodes-library.json"
        expected_file.write_text("{}")

        result = find_file_in_directory(temp_dir, "griptape[-_]nodes[-_]library.json")

        assert result == expected_file


class TestFindAllFilesInDirectory:
    """Test find_all_files_in_directory function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_find_all_files_when_directory_does_not_exist(self) -> None:
        """Test that empty list is returned when directory doesn't exist."""
        non_existent = Path("/non/existent/directory")
        result = find_all_files_in_directory(non_existent, "*.json")

        assert result == []

    def test_find_all_files_when_path_is_not_directory(self, temp_dir: Path) -> None:
        """Test that empty list is returned when path is a file, not a directory."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        result = find_all_files_in_directory(test_file, "*.json")

        assert result == []

    def test_find_all_files_when_no_files_match_pattern(self, temp_dir: Path) -> None:
        """Test that empty list is returned when no files match the pattern."""
        (temp_dir / "test.txt").write_text("content")
        (temp_dir / "another.py").write_text("content")

        result = find_all_files_in_directory(temp_dir, "*.json")

        assert result == []

    def test_find_all_files_returns_single_match(self, temp_dir: Path) -> None:
        """Test that list with single file is returned when one file matches."""
        expected_file = temp_dir / "config.json"
        expected_file.write_text("{}")
        (temp_dir / "other.txt").write_text("content")

        result = find_all_files_in_directory(temp_dir, "*.json")

        assert len(result) == 1
        assert result[0] == expected_file

    def test_find_all_files_returns_multiple_matches(self, temp_dir: Path) -> None:
        """Test that all matching files are returned."""
        file1 = temp_dir / "config1.json"
        file2 = temp_dir / "config2.json"
        file3 = temp_dir / "data.json"
        file1.write_text("{}")
        file2.write_text("{}")
        file3.write_text("{}")
        (temp_dir / "other.txt").write_text("content")

        result = find_all_files_in_directory(temp_dir, "*.json")

        assert len(result) == 3  # noqa: PLR2004
        assert set(result) == {file1, file2, file3}

    def test_find_all_files_searches_subdirectories_recursively(self, temp_dir: Path) -> None:
        """Test that function searches subdirectories recursively."""
        subdir1 = temp_dir / "sub1"
        subdir2 = temp_dir / "sub1" / "sub2"
        subdir1.mkdir()
        subdir2.mkdir()

        file1 = temp_dir / "root.json"
        file2 = subdir1 / "sub1.json"
        file3 = subdir2 / "sub2.json"
        file1.write_text("{}")
        file2.write_text("{}")
        file3.write_text("{}")

        result = find_all_files_in_directory(temp_dir, "*.json")

        assert len(result) == 3  # noqa: PLR2004
        assert set(result) == {file1, file2, file3}

    def test_find_all_files_matches_glob_pattern(self, temp_dir: Path) -> None:
        """Test that function matches files using glob patterns."""
        file1 = temp_dir / "my_library.json"
        file2 = temp_dir / "your_library.json"
        file3 = temp_dir / "config.json"
        file1.write_text("{}")
        file2.write_text("{}")
        file3.write_text("{}")

        result = find_all_files_in_directory(temp_dir, "*library*.json")

        assert len(result) == 2  # noqa: PLR2004
        assert set(result) == {file1, file2}

    def test_find_all_files_with_complex_glob_pattern(self, temp_dir: Path) -> None:
        """Test that function handles complex glob patterns."""
        file1 = temp_dir / "griptape_nodes_library.json"
        file2 = temp_dir / "griptape-nodes-library.json"
        file3 = temp_dir / "other_library.json"
        file1.write_text("{}")
        file2.write_text("{}")
        file3.write_text("{}")

        # Pattern with character class matches both underscore and hyphen versions
        result = find_all_files_in_directory(temp_dir, "griptape[-_]nodes[-_]library.json")

        assert len(result) == 2  # noqa: PLR2004
        assert set(result) == {file1, file2}
