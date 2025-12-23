"""Utilities for file and directory operations."""

from __future__ import annotations

import logging
import os
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger(__name__)


def find_file_in_directory(directory: Path, pattern: str) -> Path | None:
    """Search directory recursively for a file matching the given pattern.

    Args:
        directory: Directory to search in
        pattern: Glob pattern to match files against (e.g., '*.json', '*library*.json')

    Returns:
        Path to the first matching file if found, None otherwise.
        Logs a warning if multiple files match the pattern.

    Examples:
        >>> find_file_in_directory(Path("/workspace"), "config.json")
        Path("/workspace/subdir/config.json")
        >>> find_file_in_directory(Path("/workspace"), "*library*.json")
        Path("/workspace/libs/my_library.json")
        >>> find_file_in_directory(Path("/empty"), "missing.txt")
        None
    """
    if not directory.exists():
        logger.debug("Directory does not exist: %s", directory)
        return None

    if not directory.is_dir():
        logger.debug("Path is not a directory: %s", directory)
        return None

    matches = []
    for root, _, files_found in os.walk(directory):
        for file in files_found:
            if fnmatch(file, pattern):
                found_path = Path(root) / file
                matches.append(found_path)

    if not matches:
        logger.debug("No files matching pattern '%s' found in directory: %s", pattern, directory)
        return None

    if len(matches) > 1:
        for _match in matches:
            pass
        logger.warning(
            "Found multiple files matching pattern '%s' in %s, using first one at %s",
            pattern,
            directory,
            matches[0],
        )

    logger.debug("Found file matching pattern '%s' at: %s", pattern, matches[0])
    return matches[0]


def find_all_files_in_directory(directory: Path, pattern: str) -> list[Path]:
    """Search directory recursively for all files matching the given pattern.

    Args:
        directory: Directory to search in
        pattern: Glob pattern to match files against (e.g., '*.json', '*library*.json')

    Returns:
        List of all matching file paths. Returns empty list if none found.

    Examples:
        >>> find_all_files_in_directory(Path("/workspace"), "*.json")
        [Path("/workspace/a.json"), Path("/workspace/sub/b.json")]
        >>> find_all_files_in_directory(Path("/empty"), "*.txt")
        []
    """
    if not directory.exists():
        logger.debug("Directory does not exist: %s", directory)
        return []

    if not directory.is_dir():
        logger.debug("Path is not a directory: %s", directory)
        return []

    matches = []
    for root, _, files_found in os.walk(directory):
        for file in files_found:
            if fnmatch(file, pattern):
                found_path = Path(root) / file
                matches.append(found_path)

    if not matches:
        logger.debug("No files matching pattern '%s' found in directory: %s", pattern, directory)
    else:
        logger.debug("Found %d file(s) matching pattern '%s' in directory: %s", len(matches), pattern, directory)

    return matches


def find_files_recursive(directory: Path, pattern: str, *, skip_hidden: bool = True) -> set[Path]:
    """Search directory recursively for files matching pattern.

    Args:
        directory: Directory to search in
        pattern: Glob pattern to match files against (e.g., '*.json', '*library*.json')
        skip_hidden: If True, skip hidden directories (those starting with .). Default is True.
            This is more efficient when dealing with large hidden directories like .git, .venv, etc.

    Returns:
        Set of all matching file paths. Returns empty set if none found.

    Examples:
        >>> find_files_recursive(Path("/workspace"), "*.json")
        {Path("/workspace/a.json"), Path("/workspace/sub/b.json")}
        >>> find_files_recursive(Path("/workspace"), "*.json", skip_hidden=False)
        {Path("/workspace/a.json"), Path("/workspace/.config/b.json")}
        >>> find_files_recursive(Path("/empty"), "*.txt")
        set()
    """
    if not directory.exists():
        logger.debug("Directory does not exist: %s", directory)
        return set()

    if not directory.is_dir():
        logger.debug("Path is not a directory: %s", directory)
        return set()

    def _recurse(path: Path) -> set[Path]:
        """Recursively find files."""
        results = set()
        try:
            for item in path.iterdir():
                # Skip hidden files/directories if requested
                if skip_hidden and item.name.startswith("."):
                    continue

                if item.is_file() and fnmatch(item.name, pattern):
                    results.add(item)
                elif item.is_dir():
                    # Recurse into directories
                    results.update(_recurse(item))
        except (PermissionError, OSError) as e:
            # Skip directories we can't access
            logger.debug("Cannot access directory %s: %s", path, e)

        return results

    matches = _recurse(directory)

    if not matches:
        logger.debug("No files matching pattern '%s' found in directory: %s", pattern, directory)
    else:
        logger.debug("Found %d file(s) matching pattern '%s' in directory: %s", len(matches), pattern, directory)

    return matches
