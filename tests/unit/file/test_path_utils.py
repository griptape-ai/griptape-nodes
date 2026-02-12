"""Unit tests for path_utils utilities."""

import os
import sys
from pathlib import Path

import pytest

from griptape_nodes.file.path_utils import (
    expand_path,
    normalize_path_for_platform,
    path_needs_expansion,
    resolve_file_path,
    resolve_path_safely,
    sanitize_path_string,
    strip_surrounding_quotes,
)


class TestSanitizePathString:
    """Tests for sanitize_path_string function."""

    def test_removes_shell_escapes_from_macos_finder_path(self) -> None:
        """Test removal of shell escape characters from macOS Finder paths."""
        input_path = "/Downloads/Dragon\\'s\\ Curse/screenshot.jpg"
        expected = "/Downloads/Dragon's Curse/screenshot.jpg"
        assert sanitize_path_string(input_path) == expected

    def test_removes_shell_escapes_from_complex_path(self) -> None:
        """Test removal of shell escapes from complex paths with multiple special chars."""
        input_path = "/Test\\ Images/Level\\ 1\\ -\\ Knight\\'s\\ Quest/file.png"
        expected = "/Test Images/Level 1 - Knight's Quest/file.png"
        assert sanitize_path_string(input_path) == expected

    def test_removes_surrounding_double_quotes(self) -> None:
        """Test removal of surrounding double quotes."""
        input_path = '"/path/with spaces/file.txt"'
        expected = "/path/with spaces/file.txt"
        assert sanitize_path_string(input_path) == expected

    def test_removes_surrounding_single_quotes(self) -> None:
        """Test removal of surrounding single quotes."""
        input_path = "'/path/with spaces/file.txt'"
        expected = "/path/with spaces/file.txt"
        assert sanitize_path_string(input_path) == expected

    def test_removes_newlines_and_carriage_returns(self) -> None:
        """Test removal of newlines and carriage returns from paths."""
        input_path = "C:\\Users\\file\n\n.txt"
        expected = "C:\\Users\\file.txt"
        assert sanitize_path_string(input_path) == expected

    def test_preserves_windows_backslashes(self) -> None:
        """Test that Windows path backslashes are preserved."""
        input_path = "C:\\Users\\Documents\\file.txt"
        expected = "C:\\Users\\Documents\\file.txt"
        assert sanitize_path_string(input_path) == expected

    def test_preserves_windows_extended_length_prefix(self) -> None:
        """Test that Windows extended-length path prefix is preserved."""
        input_path = r"\\?\C:\Very\ Long\ Path\file.txt"
        expected = r"\\?\C:\Very Long Path\file.txt"
        assert sanitize_path_string(input_path) == expected

    def test_handles_path_objects(self) -> None:
        """Test conversion of Path objects to strings."""
        input_path = Path("/path/to/file")
        result = sanitize_path_string(input_path)
        # Verify exact conversion using as_posix() for cross-platform comparison
        assert result == input_path.as_posix()

    def test_strips_leading_trailing_whitespace(self) -> None:
        """Test removal of leading and trailing whitespace."""
        input_path = "  /path/to/file.txt  "
        expected = "/path/to/file.txt"
        assert sanitize_path_string(input_path) == expected


class TestStripSurroundingQuotes:
    """Tests for strip_surrounding_quotes function."""

    def test_removes_double_quotes(self) -> None:
        """Test removal of surrounding double quotes."""
        assert strip_surrounding_quotes('"test"') == "test"

    def test_removes_single_quotes(self) -> None:
        """Test removal of surrounding single quotes."""
        assert strip_surrounding_quotes("'test'") == "test"

    def test_preserves_internal_quotes(self) -> None:
        """Test that internal quotes are preserved."""
        assert strip_surrounding_quotes('test"with"quotes') == 'test"with"quotes'

    def test_preserves_unmatched_quotes(self) -> None:
        """Test that unmatched quotes are preserved."""
        assert strip_surrounding_quotes('"test') == '"test'
        assert strip_surrounding_quotes("test'") == "test'"


class TestExpandPath:
    """Tests for expand_path function."""

    def test_expands_tilde(self) -> None:
        """Test expansion of tilde to user home directory."""
        result = expand_path("~/Documents")
        assert str(result).startswith(str(Path.home()))
        assert str(result).endswith("Documents")

    def test_expands_environment_variables(self) -> None:
        """Test expansion of environment variables."""
        # Set a test environment variable
        os.environ["TEST_VAR"] = "/test/path"
        result = expand_path("$TEST_VAR/file.txt")
        # Use as_posix() to get forward slashes on all platforms for comparison
        assert result.as_posix() == "/test/path/file.txt"

    def test_returns_path_object(self) -> None:
        """Test that function returns a Path object."""
        result = expand_path("~/test")
        assert isinstance(result, Path)


class TestPathNeedsExpansion:
    """Tests for path_needs_expansion function."""

    def test_detects_tilde(self) -> None:
        """Test detection of paths starting with tilde."""
        assert path_needs_expansion("~/Documents") is True

    def test_detects_unix_env_vars(self) -> None:
        """Test detection of Unix-style environment variables."""
        assert path_needs_expansion("$HOME/file.txt") is True

    def test_detects_windows_env_vars(self) -> None:
        """Test detection of Windows-style environment variables."""
        assert path_needs_expansion("%USERPROFILE%/file.txt") is True

    def test_detects_absolute_paths(self) -> None:
        """Test detection of absolute paths."""
        # Use a platform-appropriate absolute path
        if sys.platform.startswith("win"):
            test_path = "C:\\absolute\\path"
        else:
            test_path = "/absolute/path"
        assert path_needs_expansion(test_path) is True

    def test_relative_path_no_expansion(self) -> None:
        """Test that relative paths without special chars don't need expansion."""
        assert path_needs_expansion("relative/path") is False


class TestResolvePathSafely:
    """Tests for resolve_path_safely function."""

    def test_converts_relative_to_absolute(self) -> None:
        """Test conversion of relative paths to absolute."""
        result = resolve_path_safely(Path("relative/file.txt"))
        assert result.is_absolute()

    def test_preserves_absolute_paths(self, tmp_path: Path) -> None:
        """Test that absolute paths are preserved."""
        # Use a real absolute path that works on all platforms
        test_path = tmp_path / "file.txt"
        result = resolve_path_safely(test_path)
        assert result.is_absolute()
        # Verify the paths are the same using normalized comparison
        assert result.as_posix() == test_path.as_posix()

    def test_normalizes_dot_segments(self, tmp_path: Path) -> None:
        """Test removal of . and .. segments."""
        # Use a real absolute path with .. segments
        test_path = tmp_path / "subdir" / ".." / "file.txt"
        expected = tmp_path / "file.txt"
        result = resolve_path_safely(test_path)
        # Verify the .. was normalized by comparing with expected path
        assert result.as_posix() == expected.as_posix()

    def test_works_with_nonexistent_paths(self) -> None:
        """Test that function works with non-existent paths."""
        result = resolve_path_safely(Path("/nonexistent/path/file.txt"))
        assert result.is_absolute()


class TestNormalizePathForPlatform:
    """Tests for normalize_path_for_platform function."""

    def test_returns_string(self) -> None:
        """Test that function returns a string."""
        test_path = Path("/test/path")
        result = normalize_path_for_platform(test_path)
        assert isinstance(result, str)

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-specific test")
    def test_adds_long_path_prefix_on_windows(self, tmp_path: Path) -> None:
        r"""Test that long paths get \\?\ prefix on Windows."""
        # Windows MAX_PATH limit
        windows_max_path = 260

        # Create a path longer than MAX_PATH characters
        long_subpath = "a" * 250
        long_path = tmp_path / long_subpath / "file.txt"
        long_path.parent.mkdir(parents=True, exist_ok=True)
        long_path.write_text("test")

        result = normalize_path_for_platform(long_path)
        if len(str(long_path.resolve())) >= windows_max_path:
            assert result.startswith("\\\\?\\")

    def test_sanitizes_path_string(self, tmp_path: Path) -> None:
        """Test that path is sanitized during normalization."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = normalize_path_for_platform(test_file)
        # Check for actual newline and carriage return characters, not the string sequences
        assert "\n" not in result
        assert "\r" not in result


class TestResolveFilePath:
    """Tests for resolve_file_path function."""

    def test_expands_absolute_paths(self, tmp_path: Path) -> None:
        """Test expansion of absolute paths."""
        result = resolve_file_path("/absolute/path", tmp_path)
        assert result.is_absolute()

    def test_expands_tilde_paths(self, tmp_path: Path) -> None:
        """Test expansion of tilde paths."""
        result = resolve_file_path("~/Documents", tmp_path)
        assert result.is_absolute()
        assert str(result).startswith(str(Path.home()))

    def test_resolves_relative_paths_against_base_dir(self, tmp_path: Path) -> None:
        """Test resolution of relative paths against base directory."""
        result = resolve_file_path("relative/file.txt", tmp_path)
        assert result.is_absolute()
        assert str(result).startswith(str(tmp_path))
