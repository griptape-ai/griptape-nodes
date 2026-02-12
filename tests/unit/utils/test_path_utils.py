"""Tests for path_utils module."""

from pathlib import Path

from griptape_nodes.utils.path_utils import (
    get_workspace_relative_path,
    parse_filename_components,
    resolve_workspace_path,
)


class TestResolveWorkspacePath:
    """Test resolve_workspace_path function."""

    def test_relative_path(self) -> None:
        """Test resolving a relative path."""
        base = Path("/workspace")
        result = resolve_workspace_path(Path("file.txt"), base)
        assert result == Path("/workspace/file.txt")

    def test_absolute_path(self) -> None:
        """Test resolving an absolute path."""
        base = Path("/workspace")
        result = resolve_workspace_path(Path("/tmp/file.txt"), base)  # noqa: S108
        assert result == Path("/tmp/file.txt").resolve()  # noqa: S108


class TestGetWorkspaceRelativePath:
    """Test get_workspace_relative_path function."""

    def test_absolute_path_in_workspace(self) -> None:
        """Test converting absolute path to relative."""
        base = Path("/workspace")
        result = get_workspace_relative_path(Path("/workspace/subdir/file.txt"), base)
        assert result == Path("subdir/file.txt")

    def test_relative_path(self) -> None:
        """Test converting relative path."""
        base = Path("/workspace")
        result = get_workspace_relative_path(Path("file.txt"), base)
        assert result == Path("file.txt")


class TestParseFilenameComponents:
    """Test parse_filename_components function."""

    def test_filename_with_single_extension(self) -> None:
        """Test parsing filename with single extension."""
        base, ext = parse_filename_components("image.png")
        assert base == "image"
        assert ext == "png"

    def test_filename_with_multi_dot_extension(self) -> None:
        """Test parsing filename with multi-dot extension like .tar.gz."""
        base, ext = parse_filename_components("output.tar.gz")
        assert base == "output.tar"
        assert ext == "gz"

    def test_filename_without_extension(self) -> None:
        """Test parsing filename without extension uses default."""
        base, ext = parse_filename_components("test")
        assert base == "test"
        assert ext == "png"

    def test_filename_without_extension_custom_default(self) -> None:
        """Test parsing filename without extension uses custom default."""
        base, ext = parse_filename_components("test", default_extension="jpg")
        assert base == "test"
        assert ext == "jpg"

    def test_filename_with_dot_prefix(self) -> None:
        """Test parsing hidden file with extension."""
        base, ext = parse_filename_components(".config.json")
        assert base == ".config"
        assert ext == "json"

    def test_filename_hidden_without_extension(self) -> None:
        """Test parsing hidden file without extension uses default extension."""
        base, ext = parse_filename_components(".gitignore")
        assert base == ".gitignore"
        assert ext == "png"

    def test_empty_string(self) -> None:
        """Test parsing empty string uses default extension."""
        base, ext = parse_filename_components("")
        assert base == "."
        assert ext == "png"

    def test_only_extension(self) -> None:
        """Test parsing string that is only a dot-prefixed name uses default extension."""
        base, ext = parse_filename_components(".txt")
        assert base == ".txt"
        assert ext == "png"

    def test_multiple_dots_in_filename(self) -> None:
        """Test parsing filename with multiple dots."""
        base, ext = parse_filename_components("my.file.name.txt")
        assert base == "my.file.name"
        assert ext == "txt"
