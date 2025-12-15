"""Path utility functions."""

from pathlib import Path


def resolve_workspace_path(path: Path, workspace_directory: Path) -> Path:
    """Resolve a path, treating relative paths as workspace-relative.

    If the path is relative, it's resolved relative to the workspace directory.
    If the path is absolute, it's resolved as-is.

    Args:
        path: The path to resolve (can be relative or absolute)
        workspace_directory: The workspace directory to use for relative paths

    Returns:
        The resolved absolute path

    Example:
        >>> workspace = Path("/workspace")
        >>> resolve_workspace_path(Path("file.txt"), workspace)
        Path("/workspace/file.txt")
        >>> resolve_workspace_path(Path("/tmp/file.txt"), workspace)
        Path("/tmp/file.txt")
    """
    if not path.is_absolute():
        return (workspace_directory / path).resolve()
    return path.resolve()


def get_workspace_relative_path(path: Path, workspace_directory: Path) -> Path:
    """Convert a path to be relative to the workspace directory.

    Takes an absolute or relative path and returns it as a path relative to
    the workspace directory.

    Args:
        path: The path to convert (can be relative or absolute)
        workspace_directory: The workspace directory to make the path relative to

    Returns:
        Path relative to workspace_directory

    Example:
        >>> workspace = Path("/workspace")
        >>> get_workspace_relative_path(Path("/workspace/subdir/file.txt"), workspace)
        Path("subdir/file.txt")
        >>> get_workspace_relative_path(Path("file.txt"), workspace)
        Path("file.txt")
    """
    absolute_path = resolve_workspace_path(path, workspace_directory)
    return absolute_path.relative_to(workspace_directory.resolve())
