"""Path utility functions."""

from pathlib import Path


def resolve_workspace_path(path: Path, base_directory: Path) -> Path:
    """Resolve a path, treating relative paths as relative to a base directory.

    If the path is relative, it's resolved relative to the base directory.
    If the path is absolute, it's resolved as-is.

    This utility works with any base directory - workspace_directory, project_base_dir,
    or any other base path.

    Args:
        path: The path to resolve (can be relative or absolute)
        base_directory: The base directory to use for relative paths

    Returns:
        The resolved absolute path

    Example:
        >>> base = Path("/workspace")
        >>> resolve_workspace_path(Path("file.txt"), base)
        Path("/workspace/file.txt")
        >>> resolve_workspace_path(Path("/tmp/file.txt"), base)
        Path("/tmp/file.txt")
    """
    if not path.is_absolute():
        return (base_directory / path).resolve()
    return path.resolve()


def get_workspace_relative_path(path: Path, base_directory: Path) -> Path:
    """Convert a path to be relative to a base directory.

    Takes an absolute or relative path and returns it as a path relative to
    the base directory.

    This utility works with any base directory - workspace_directory, project_base_dir,
    or any other base path.

    Args:
        path: The path to convert (can be relative or absolute)
        base_directory: The base directory to make the path relative to

    Returns:
        Path relative to base_directory

    Example:
        >>> base = Path("/workspace")
        >>> get_workspace_relative_path(Path("/workspace/subdir/file.txt"), base)
        Path("subdir/file.txt")
        >>> get_workspace_relative_path(Path("file.txt"), base)
        Path("file.txt")
    """
    absolute_path = resolve_workspace_path(path, base_directory)
    return absolute_path.relative_to(base_directory.resolve())


def parse_filename_components(filename: str, default_extension: str = "png") -> tuple[str, str]:
    """Parse filename into base and extension using pathlib.

    Args:
        filename: Filename to parse
        default_extension: Extension to use if filename has none

    Returns:
        Tuple of (base, extension)

    Example:
        >>> parse_filename_components("image.png")
        ("image", "png")
        >>> parse_filename_components("output.tar.gz")
        ("output.tar", "gz")
        >>> parse_filename_components("test")
        ("test", "png")
    """
    path = Path(filename)
    if path.suffix:
        return path.stem, path.suffix.lstrip(".")
    return str(path), default_extension
