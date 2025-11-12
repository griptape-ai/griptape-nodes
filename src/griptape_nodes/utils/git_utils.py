"""Git utilities for library updates."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

import pygit2

from griptape_nodes.utils.file_utils import find_all_files_in_directory, find_file_in_directory

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Base exception for git operations."""


class GitRepositoryError(GitError):
    """Raised when a path is not a valid git repository."""


class GitRemoteError(GitError):
    """Raised when git remote operations fail."""


class GitBranchError(GitError):
    """Raised when git branch operations fail."""


class GitCloneError(GitError):
    """Raised when git clone operations fail."""


class GitPullError(GitError):
    """Raised when git pull operations fail."""


def is_git_url(url: str) -> bool:
    """Check if a string is a git URL.

    Args:
        url: The URL to check.

    Returns:
        bool: True if the string is a git URL, False otherwise.
    """
    git_url_patterns = (
        "http://",
        "https://",
        "git://",
        "ssh://",
        "git@",
    )
    return url.startswith(git_url_patterns)


def is_git_repository(path: Path) -> bool:
    """Check if a directory is a git repository.

    Args:
        path: The directory path to check.

    Returns:
        bool: True if the directory is a git repository, False otherwise.
    """
    if not path.exists():
        return False
    if not path.is_dir():
        return False

    try:
        pygit2.discover_repository(str(path))
    except pygit2.GitError:
        return False
    else:
        return True


def get_git_remote(library_path: Path) -> str | None:
    """Get the git remote URL for a library directory.

    Args:
        library_path: The path to the library directory.

    Returns:
        str | None: The remote URL if found, None if not a git repository or no remote configured.

    Raises:
        GitRemoteError: If an error occurs while accessing the git remote.
    """
    if not is_git_repository(library_path):
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            return None

        repo = pygit2.Repository(repo_path)

        # Access remote by indexing (raises KeyError if not found)
        try:
            remote = repo.remotes["origin"]
        except (KeyError, IndexError):
            return None
        else:
            return remote.url

    except pygit2.GitError as e:
        msg = f"Error getting git remote for {library_path}: {e}"
        logger.error(msg)
        raise GitRemoteError(msg) from e


def get_current_branch(library_path: Path) -> str | None:
    """Get the current branch name for a library directory.

    Args:
        library_path: The path to the library directory.

    Returns:
        str | None: The current branch name if found, None if not a git repository or detached HEAD.

    Raises:
        GitBranchError: If an error occurs while getting the current branch.
    """
    if not is_git_repository(library_path):
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            return None

        repo = pygit2.Repository(repo_path)

        # Check if HEAD is detached
        if repo.head_is_detached:
            logger.debug("Repository at %s has detached HEAD", library_path)
            return None

    except pygit2.GitError as e:
        msg = f"Error getting current branch for {library_path}: {e}"
        logger.error(msg)
        raise GitBranchError(msg) from e
    else:
        # Get the current branch name
        return repo.head.shorthand


def get_git_repository_root(library_path: Path) -> Path | None:
    """Get the root directory of the git repository containing the given path.

    Args:
        library_path: A path within a git repository.

    Returns:
        Path | None: The root directory of the git repository, or None if not in a git repository.

    Raises:
        GitRepositoryError: If an error occurs while accessing the git repository.
    """
    if not is_git_repository(library_path):
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            return None

        # discover_repository returns path to .git directory
        # For a normal repo: /path/to/repo/.git
        # For a bare repo: /path/to/repo.git
        git_dir = Path(repo_path)

        # Check if it's a bare repository
        if git_dir.name.endswith(".git") and git_dir.is_dir():
            repo = pygit2.Repository(repo_path)
            if repo.is_bare:
                return git_dir

    except pygit2.GitError as e:
        msg = f"Error getting git repository root for {library_path}: {e}"
        logger.error(msg)
        raise GitRepositoryError(msg) from e
    else:
        # Normal repository - return parent of .git directory
        return git_dir.parent


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


def clone_and_get_version(remote_url: str) -> str:
    """Clone a git repository to a temporary directory and extract the library version.

    Args:
        remote_url: The git remote URL to clone (HTTPS or SSH).

    Returns:
        str: The library version from griptape_nodes_library.json.

    Raises:
        GitCloneError: If cloning fails or library metadata is invalid.
    """
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
                logger.error(msg)
                raise GitCloneError(msg)

        except pygit2.GitError as e:
            msg = f"Git error while cloning {remote_url}: {e}"
            logger.error(msg)
            raise GitCloneError(msg) from e

        # Recursively search for griptape_nodes_library.json file
        library_json_path = find_file_in_directory(Path(temp_dir), "griptape[-_]nodes[-_]library.json")
        if library_json_path is None:
            msg = f"No library JSON file found in cloned repository from {remote_url}"
            logger.error(msg)
            raise GitCloneError(msg)

        try:
            with library_json_path.open() as f:
                library_data = json.load(f)
        except json.JSONDecodeError as e:
            msg = f"JSON decode error reading library metadata from {remote_url}: {e}"
            logger.error(msg)
            raise GitCloneError(msg) from e

        if "metadata" not in library_data:
            msg = f"No metadata found in griptape_nodes_library.json from {remote_url}"
            logger.error(msg)
            raise GitCloneError(msg)

        if "library_version" not in library_data["metadata"]:
            msg = f"No library_version found in metadata from {remote_url}"
            logger.error(msg)
            raise GitCloneError(msg)

        return library_data["metadata"]["library_version"]


def git_pull_rebase(library_path: Path) -> None:
    """Perform a git pull --rebase on a library directory.

    Args:
        library_path: The path to the library directory.

    Raises:
        GitRepositoryError: If the path is not a valid git repository.
        GitPullError: If the pull --rebase operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot pull: {library_path} is not a git repository"
        logger.error(msg)
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            logger.error(msg)
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Check for detached HEAD
        if repo.head_is_detached:
            msg = f"Repository at {library_path} has detached HEAD"
            logger.error(msg)
            raise GitPullError(msg)

        # Get the current branch
        current_branch = repo.branches.get(repo.head.shorthand)
        if current_branch is None:
            msg = f"Cannot get current branch for repository at {library_path}"
            logger.error(msg)
            raise GitPullError(msg)

        # Check for upstream
        upstream = current_branch.upstream
        if upstream is None:
            msg = f"No upstream branch set for {current_branch.branch_name} at {library_path}"
            logger.error(msg)
            raise GitPullError(msg)

        # Check for origin remote
        try:
            _ = repo.remotes["origin"]
        except (KeyError, IndexError) as e:
            msg = f"No origin remote found for repository at {library_path}"
            logger.error(msg)
            raise GitPullError(msg) from e

    except pygit2.GitError as e:
        msg = f"Git error during pull --rebase at {library_path}: {e}"
        logger.error(msg)
        raise GitPullError(msg) from e

    # Use subprocess to call git pull --rebase
    # This is more reliable than implementing rebase with pygit2
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase"],  # noqa: S607
            cwd=str(library_path),
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            msg = f"Git pull --rebase failed at {library_path}: {result.stderr}"
            logger.error(msg)
            raise GitPullError(msg)

    except subprocess.SubprocessError as e:
        msg = f"Subprocess error during pull --rebase at {library_path}: {e}"
        logger.error(msg)
        raise GitPullError(msg) from e


def switch_branch(library_path: Path, branch_name: str) -> None:
    """Switch to a different branch in a library directory.

    Fetches from remote first, then checks out the specified branch.
    If the branch doesn't exist locally, creates a tracking branch from remote.

    Args:
        library_path: The path to the library directory.
        branch_name: The name of the branch to switch to.

    Raises:
        GitRepositoryError: If the path is not a valid git repository.
        GitBranchError: If the branch switch operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot switch branch: {library_path} is not a git repository"
        logger.error(msg)
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            logger.error(msg)
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Get origin remote
        try:
            remote = repo.remotes["origin"]
        except (KeyError, IndexError) as e:
            msg = f"No origin remote found for repository at {library_path}"
            logger.error(msg)
            raise GitBranchError(msg) from e

        # Fetch from remote first
        remote.fetch()

        # Try to find the branch locally first
        local_branch = repo.branches.get(branch_name)

        if local_branch is not None:
            # Branch exists locally, just check it out
            repo.checkout(local_branch)
            logger.info("Checked out existing local branch %s at %s", branch_name, library_path)
            return

        # Branch doesn't exist locally, try to find it on remote
        remote_branch_name = f"origin/{branch_name}"
        remote_branch = repo.branches.get(remote_branch_name)

        if remote_branch is None:
            msg = f"Branch {branch_name} not found locally or on remote at {library_path}"
            logger.error(msg)
            raise GitBranchError(msg)

        # Create local tracking branch from remote
        commit = repo.get(remote_branch.target)
        if commit is None:
            msg = f"Failed to get commit for remote branch {remote_branch_name} at {library_path}"
            logger.error(msg)
            raise GitBranchError(msg)

        new_branch = repo.branches.local.create(branch_name, commit)  # type: ignore[arg-type]
        new_branch.upstream = remote_branch

        # Checkout the new branch
        repo.checkout(new_branch)
        logger.info(
            "Created and checked out tracking branch %s from %s at %s", branch_name, remote_branch_name, library_path
        )

    except pygit2.GitError as e:
        msg = f"Git error during branch switch at {library_path}: {e}"
        logger.error(msg)
        raise GitBranchError(msg) from e


def _is_ssh_url(url: str) -> bool:
    """Check if a URL is an SSH URL format.

    Args:
        url: The URL to check.

    Returns:
        bool: True if the URL is SSH format, False otherwise.
    """
    return url.startswith(("git@", "ssh://"))


def _convert_ssh_to_https(ssh_url: str) -> str:
    """Convert SSH URL to HTTPS URL.

    Args:
        ssh_url: The SSH URL to convert.

    Returns:
        str: The HTTPS URL, or original URL if not SSH format.

    Examples:
        git@github.com:user/repo.git -> https://github.com/user/repo.git
        ssh://git@github.com/user/repo.git -> https://github.com/user/repo.git
    """
    # Handle ssh:// format
    if ssh_url.startswith("ssh://"):
        return re.sub(r"^ssh://(?:git@)?([^/]+)/", r"https://\1/", ssh_url)

    # Handle git@ format
    if ssh_url.startswith("git@"):
        return re.sub(r"^git@([^:]+):", r"https://\1/", ssh_url)

    # Not an SSH URL, return unchanged
    return ssh_url


def clone_library(git_url: str, target_path: Path, branch_tag_commit: str | None = None) -> None:
    """Clone a git repository to a target directory.

    Args:
        git_url: The git repository URL to clone (HTTPS or SSH).
        target_path: The target directory path to clone into.
        branch_tag_commit: Optional branch, tag, or commit to checkout after cloning.

    Raises:
        GitCloneError: If cloning fails or target path already exists.
    """
    if target_path.exists():
        msg = f"Cannot clone: target path {target_path} already exists"
        logger.error(msg)
        raise GitCloneError(msg)

    # Convert SSH URLs to HTTPS for compatibility
    original_url = git_url
    if _is_ssh_url(git_url):
        git_url = _convert_ssh_to_https(git_url)
        logger.info("Converted SSH URL to HTTPS: %s -> %s", original_url, git_url)

    try:
        # Clone the repository
        repo = pygit2.clone_repository(git_url, str(target_path))
        if repo is None:
            msg = f"Failed to clone repository from {git_url}"
            logger.error(msg)
            raise GitCloneError(msg)

        # Checkout specific branch/tag/commit if provided
        if branch_tag_commit:
            # Try to resolve as a branch first
            try:
                branch = repo.branches[branch_tag_commit]
                repo.checkout(branch)
                logger.info("Checked out branch %s", branch_tag_commit)
            except (pygit2.GitError, KeyError, IndexError):
                # Try to resolve as a tag or commit
                try:
                    commit_obj = repo.revparse_single(branch_tag_commit)
                    repo.checkout_tree(commit_obj)
                    repo.set_head(commit_obj.id)
                    logger.info("Checked out %s", branch_tag_commit)
                except pygit2.GitError as e:
                    msg = f"Failed to checkout {branch_tag_commit}: {e}"
                    logger.error(msg)
                    raise GitCloneError(msg) from e

    except pygit2.GitError as e:
        msg = f"Git error while cloning {git_url} to {target_path}: {e}"
        logger.error(msg)
        raise GitCloneError(msg) from e
