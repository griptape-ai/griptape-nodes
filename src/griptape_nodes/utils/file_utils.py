"""Utilities for file and directory operations."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("griptape_nodes")


def find_file_in_directory(directory: Path, filename: str) -> Path | None:
    """Search directory recursively for a file with the exact filename.

    Args:
        directory: Directory to search in
        filename: Exact filename to search for (e.g., 'library.json')

    Returns:
        Path to the first matching file if found, None otherwise

    Examples:
        >>> find_file_in_directory(Path("/workspace"), "config.json")
        Path("/workspace/subdir/config.json")
        >>> find_file_in_directory(Path("/empty"), "missing.txt")
        None
    """
    if not directory.exists():
        logger.debug("Directory does not exist: %s", directory)
        return None

    if not directory.is_dir():
        logger.debug("Path is not a directory: %s", directory)
        return None

    for root, _, files_found in os.walk(directory):
        for file in files_found:
            if file == filename:
                found_path = Path(root) / file
                logger.debug("Found file '%s' at: %s", filename, found_path)
                return found_path

    logger.debug("File '%s' not found in directory: %s", filename, directory)
    return None
