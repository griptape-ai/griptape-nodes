"""Library-specific utilities for managing node libraries."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pygit2

from griptape_nodes.utils.file_utils import find_all_files_in_directory, find_file_in_directory
from griptape_nodes.utils.git_utils import GitCloneError, get_git_repository_root

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
    """Clone a git repository to a temporary directory and extract the library version and commit SHA.

    Args:
        remote_url: The git remote URL to clone (HTTPS or SSH).

    Returns:
        tuple[str, str]: A tuple of (library_version, commit_sha) from the cloned repository.

    Raises:
        GitCloneError: If cloning fails or library metadata is invalid.
    """
    from griptape_nodes.utils.git_utils import _convert_ssh_to_https, _is_ssh_url

    # Convert SSH URLs to HTTPS for compatibility
    original_url = remote_url
    if _is_ssh_url(remote_url):
        remote_url = _convert_ssh_to_https(remote_url)
        logger.info("Converted SSH URL to HTTPS: %s -> %s", original_url, remote_url)

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            repo = pygit2.clone_repository(remote_url, temp_dir)
            if repo is None:
                msg = f"Failed to clone repository from {remote_url}"
                raise GitCloneError(msg)

        except pygit2.GitError as e:
            msg = f"Git error while cloning {remote_url}: {e}"
            raise GitCloneError(msg) from e

        # Recursively search for griptape_nodes_library.json file
        library_json_path = find_file_in_directory(Path(temp_dir), "griptape[-_]nodes[-_]library.json")
        if library_json_path is None:
            msg = f"No library JSON file found in cloned repository from {remote_url}"
            raise GitCloneError(msg)

        try:
            with library_json_path.open() as f:
                library_data = json.load(f)
        except json.JSONDecodeError as e:
            msg = f"JSON decode error reading library metadata from {remote_url}: {e}"
            raise GitCloneError(msg) from e

        if "metadata" not in library_data:
            msg = f"No metadata found in griptape_nodes_library.json from {remote_url}"
            raise GitCloneError(msg)

        if "library_version" not in library_data["metadata"]:
            msg = f"No library_version found in metadata from {remote_url}"
            raise GitCloneError(msg)

        library_version = library_data["metadata"]["library_version"]
        commit_sha = str(repo.head.target)

        return (library_version, commit_sha)
