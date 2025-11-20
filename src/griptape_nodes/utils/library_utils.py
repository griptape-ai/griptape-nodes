"""Library-specific utilities for managing node libraries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.utils.file_utils import find_all_files_in_directory
from griptape_nodes.utils.git_utils import (
    get_git_repository_root,
    sparse_checkout_library_json,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def is_monorepo(library_path: Path) -> bool:
    """Check if a library is in a monorepo (git repository with multiple library JSON files).

    Args:
        library_path: The path to the library directory.

    Returns:
        bool: True if the git repository contains multiple library JSON files, False otherwise.
    """
    # Get the git repository root
    repo_root = get_git_repository_root(library_path)
    if repo_root is None:
        return False

    # Search for all library JSON files in the repository
    library_json_files = find_all_files_in_directory(repo_root, "griptape[-_]nodes[-_]library.json")

    # Monorepo if more than 1 library JSON file exists
    return len(library_json_files) > 1


def clone_and_get_library_version(remote_url: str) -> tuple[str, str]:
    """Fetch library version and commit SHA using sparse checkout for efficiency.

    Uses sparse checkout to download only the library JSON file instead of the entire repository,
    significantly reducing bandwidth and time for update checks.

    Args:
        remote_url: The git remote URL (HTTPS or SSH).

    Returns:
        tuple[str, str]: A tuple of (library_version, commit_sha) from the repository.

    Raises:
        GitCloneError: If sparse checkout fails or library metadata is invalid.
    """
    library_version, commit_sha, _ = sparse_checkout_library_json(remote_url)
    return (library_version, commit_sha)
