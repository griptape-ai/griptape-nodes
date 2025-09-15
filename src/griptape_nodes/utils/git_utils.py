"""Git utilities for repository operations and URL parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import git


@dataclass
class GitUrlComponents:
    """Components extracted from a Git URL."""

    base_url: str
    branch: str
    subdir: str | None
    url_type: str  # 'directory', 'file', 'repo'
    detected_from_url: bool
    filename: str | None = None


def parse_git_url(url: str) -> GitUrlComponents:
    """Parse a Git URL to extract repository, branch, and subdirectory information.

    Supports both directory URLs (/tree/, /src/) and file URLs (/blob/) from
    GitHub, GitLab, and Bitbucket.

    Args:
        url: Git URL to parse

    Returns:
        GitUrlComponents with extracted information
    """
    # URL decode to handle encoded characters
    url = unquote(url).rstrip("/")

    # Try to match various URL patterns
    patterns = [
        # GitHub patterns
        (r"^(https://github\.com/[^/]+/[^/]+)/tree/([^/]+)(?:/(.+))?$", "directory"),
        (r"^(https://github\.com/[^/]+/[^/]+)/blob/([^/]+)/(.+)$", "file"),
        # GitLab patterns
        (r"^(https://gitlab\.com/[^/]+/[^/]+)/-/tree/([^/]+)(?:/(.+))?$", "directory"),
        (r"^(https://gitlab\.com/[^/]+/[^/]+)/-/blob/([^/]+)/(.+)$", "file"),
        # Bitbucket patterns
        (r"^(https://bitbucket\.org/[^/]+/[^/]+)/src/([^/]+)(?:/(.+))?$", "src"),
    ]

    for pattern, url_type in patterns:
        match = re.match(pattern, url)
        if match:
            base_url, branch, path = match.groups()

            # Handle file URLs
            if url_type == "file":
                return _handle_file_url(base_url, branch, path, "file")

            # Handle Bitbucket special case
            if url_type == "src" and path and path.endswith(".json"):
                return _handle_file_url(base_url, branch, path, "file")

            # Handle directory URLs
            return GitUrlComponents(
                base_url=base_url,
                branch=branch,
                subdir=path or None,
                url_type="directory" if path else "repo",
                detected_from_url=True,
            )

    # Fallback: treat as plain repository URL
    return GitUrlComponents(
        base_url=url,
        branch="main",
        subdir=None,
        url_type="repo",
        detected_from_url=False,
    )


def _handle_file_url(base_url: str, branch: str, path: str, url_type: str) -> GitUrlComponents:
    """Handle file URLs by extracting subdirectory from file path.

    Args:
        base_url: Base repository URL
        branch: Branch name
        path: Full file path
        url_type: URL type identifier

    Returns:
        GitUrlComponents with subdirectory extracted from file path
    """
    path_parts = Path(path).parts
    filename = path_parts[-1] if path_parts else ""
    subdir = str(Path(*path_parts[:-1])) if len(path_parts) > 1 else None

    return GitUrlComponents(
        base_url=base_url,
        branch=branch,
        subdir=subdir,
        url_type=url_type,
        detected_from_url=True,
        filename=filename,
    )


def is_git_url(source: str) -> bool:
    """Check if a source string is a Git URL.

    Args:
        source: The source string to check

    Returns:
        True if the source appears to be a Git URL
    """
    git_indicators = [
        source.startswith("https://github.com/"),
        source.startswith("https://gitlab.com/"),
        source.startswith("https://bitbucket.org/"),
        source.startswith("git@"),
        source.startswith("ssh://"),
        source.endswith(".git"),
        "github.com" in source,
        "gitlab.com" in source,
        "bitbucket.org" in source,
    ]

    return any(git_indicators)


def sanitize_repo_name(git_url: str) -> str:
    """Create a safe directory name from a Git URL.

    Args:
        git_url: The Git repository URL

    Returns:
        A sanitized directory name
    """
    # Extract the repository name from the URL
    git_url = git_url.removesuffix(".git")

    # Get the last part of the URL path
    repo_name = git_url.split("/")[-1]

    # Replace unsafe characters with underscores
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", repo_name)

    return safe_name


def clone_subdirectory(git_url: str, clone_path: Path, branch: str, subdir: str) -> None:
    """Clone only a specific subdirectory from a Git repository.

    Downloads only the specified subdirectory and its contents,
    ignoring all other files and directories in the repository.

    Args:
        git_url: URL of the Git repository to clone
        clone_path: Local path where repository should be cloned
        branch: Git branch to checkout
        subdir: Exact subdirectory path to include (only this directory will be downloaded)

    Raises:
        git.GitCommandError: If any git command fails
    """
    # Initialize empty repository
    repo = git.Repo.init(clone_path)

    # Add remote origin
    origin = repo.create_remote("origin", git_url)

    # Configure Git to only download the specified directory
    with repo.config_writer() as config:
        config.set_value("core", "sparseCheckout", "true")

    # Set which directory to include
    checkout_file = clone_path / ".git" / "info" / "sparse-checkout"
    checkout_file.parent.mkdir(parents=True, exist_ok=True)

    # Only include the specific subdirectory and its contents
    with checkout_file.open("w", encoding="utf-8") as f:
        f.write(f"{subdir}/\n")

    # Fetch the specific branch
    origin.fetch(branch)

    # Create and checkout the branch
    repo.create_head(branch, origin.refs[branch])
    repo.heads[branch].checkout()
