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
