"""Utilities for working with git repositories."""

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import pygit2

logger = logging.getLogger("griptape_nodes")


def is_git_url(url: str) -> bool:
    """Check if a string is a git URL.

    Args:
        url: String to check

    Returns:
        True if the string appears to be a git URL, False otherwise

    Examples:
        >>> is_git_url("https://github.com/user/repo.git")
        True
        >>> is_git_url("git@github.com:user/repo.git")
        True
        >>> is_git_url("/path/to/local/file.json")
        False
    """
    if not url:
        return False

    # Check for common git URL patterns
    # HTTPS/HTTP URLs, SSH URLs, and file:// URLs for local git repos
    return url.startswith(("https://", "http://", "git://", "git@", "ssh://", "file://"))


def get_repo_name_from_url(url: str) -> str:
    """Extract a sanitized repository name from a git URL.

    Args:
        url: Git URL to extract name from

    Returns:
        Sanitized name suitable for use as a directory name

    Examples:
        >>> get_repo_name_from_url("https://github.com/user/my-repo.git")
        'my-repo'
        >>> get_repo_name_from_url("git@gitlab.com:org/project.git")
        'project'
    """
    # Handle SSH URLs (git@host:path)
    if url.startswith("git@"):
        # Extract path after the colon
        if ":" in url:
            path = url.split(":", 1)[1]
        else:
            path = url
    else:
        # Use urlparse for standard URLs
        parsed = urlparse(url)
        path = parsed.path

    # Remove leading/trailing slashes and .git extension
    path = path.strip("/")
    path = path.removesuffix(".git")

    # Get just the repository name (last part of path)
    repo_name = path.split("/")[-1]

    # Sanitize: replace problematic characters with underscores
    repo_name = re.sub(r"[^\w\-.]", "_", repo_name)

    return repo_name


def clone_or_update_git_library(url: str, target_dir: Path, ref: str | None = None) -> Path:
    """Clone a git repository or update it if it already exists.

    Args:
        url: Git repository URL to clone
        target_dir: Directory to clone into (will be created if it doesn't exist)
        ref: Optional branch, tag, or commit to checkout (defaults to default branch)

    Returns:
        Path to the cloned repository directory

    Raises:
        RuntimeError: If cloning or updating fails
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    if (target_dir / ".git").exists():
        return _update_existing_repository(target_dir, ref)
    return _clone_new_repository(url, target_dir, ref)


def _checkout_ref(repo: pygit2.Repository, ref: str) -> None:
    """Check out a specific ref (branch, tag, or commit) in a repository.

    Args:
        repo: The git repository
        ref: Branch, tag, or commit to checkout

    Raises:
        KeyError: If the ref cannot be found
    """
    # Try to find the ref (branch, tag, or commit)
    commit = repo.revparse_single(ref)
    repo.checkout_tree(commit)
    # Update HEAD
    if repo.references.get(f"refs/heads/{ref}"):
        repo.set_head(f"refs/heads/{ref}")
    else:
        repo.set_head(commit.id)


def _update_to_latest(repo: pygit2.Repository) -> None:
    """Update repository to latest commit on default branch.

    Args:
        repo: The git repository to update
    """
    # Get the default branch
    default_branch = repo.head.shorthand
    # Fast-forward merge with remote
    remote_ref = repo.references.get(f"refs/remotes/origin/{default_branch}")
    if remote_ref:
        # Get the commit object from the remote reference
        remote_commit = repo[remote_ref.target].peel(pygit2.Commit)
        # Checkout the tree from the remote reference
        repo.checkout_tree(remote_commit)
        # Update or create the local branch reference
        local_ref = repo.references.get(f"refs/heads/{default_branch}")
        if local_ref:
            local_ref.set_target(remote_ref.target)
        else:
            # Create local branch if it doesn't exist
            repo.create_branch(default_branch, remote_commit)
        # Set HEAD to the local branch
        repo.set_head(f"refs/heads/{default_branch}")


def _update_existing_repository(target_dir: Path, ref: str | None) -> Path:
    """Update an existing git repository.

    Args:
        target_dir: Directory containing the existing repository
        ref: Optional branch, tag, or commit to checkout

    Returns:
        Path to the repository directory

    Raises:
        RuntimeError: If updating fails
    """
    logger.debug("Repository already exists at %s, fetching updates", target_dir)
    try:
        repo = pygit2.Repository(str(target_dir))

        # Fetch updates from remote
        remote = repo.remotes["origin"]
        remote.fetch()

        # Checkout the specified ref if provided
        if ref:
            try:
                _checkout_ref(repo, ref)
            except KeyError as e:
                logger.warning("Could not find ref '%s' in repository, using default branch: %s", ref, e)
        else:
            _update_to_latest(repo)

        logger.info("Updated git repository at %s", target_dir)
        return target_dir  # noqa: TRY300

    except Exception as e:
        error_msg = f"Failed to update git repository at {target_dir}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def _clone_new_repository(url: str, target_dir: Path, ref: str | None) -> Path:
    """Clone a new git repository.

    Args:
        url: Git repository URL to clone
        target_dir: Directory to clone into
        ref: Optional branch, tag, or commit to checkout

    Returns:
        Path to the cloned repository directory

    Raises:
        RuntimeError: If cloning fails
    """
    logger.info("Cloning git repository from %s to %s", url, target_dir)
    try:
        # Clone the repository
        repo = pygit2.clone_repository(url, str(target_dir))

        # Checkout the specified ref if provided
        if ref:
            try:
                _checkout_ref(repo, ref)
            except KeyError as e:
                logger.warning("Could not find ref '%s' in repository, using default branch: %s", ref, e)

        logger.info("Successfully cloned git repository to %s", target_dir)
        return target_dir  # noqa: TRY300

    except Exception as e:
        error_msg = f"Failed to clone git repository from {url}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
