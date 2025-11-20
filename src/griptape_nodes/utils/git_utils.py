"""Git utilities for library updates."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import pygit2

logger = logging.getLogger("griptape_nodes")


class GitError(Exception):
    """Base exception for git operations."""


class GitRepositoryError(GitError):
    """Raised when a path is not a valid git repository."""


class GitRemoteError(GitError):
    """Raised when git remote operations fail."""


class GitRefError(GitError):
    """Raised when git ref operations fail."""


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


def normalize_github_url(url_or_shorthand: str) -> str:
    """Normalize a GitHub URL or shorthand to a full HTTPS git URL.

    Converts GitHub shorthand (e.g., "owner/repo") to full HTTPS URLs.
    Ensures .git suffix on GitHub URLs. Passes through non-GitHub URLs unchanged.

    Args:
        url_or_shorthand: Either a full git URL or GitHub shorthand (e.g., "user/repo").

    Returns:
        A normalized HTTPS git URL.

    Examples:
        "griptape-ai/griptape-nodes-library-topazlabs" -> "https://github.com/griptape-ai/griptape-nodes-library-topazlabs.git"
        "https://github.com/user/repo" -> "https://github.com/user/repo.git"
        "git@github.com:user/repo.git" -> "git@github.com:user/repo.git"
        "https://gitlab.com/user/repo" -> "https://gitlab.com/user/repo"
    """
    url = url_or_shorthand.strip().rstrip("/")

    # Check if it's GitHub shorthand: owner/repo (no protocol, single slash, no domain)
    if not is_git_url(url) and "/" in url and url.count("/") == 1:
        # Assume GitHub shorthand
        return f"https://github.com/{url}.git"

    # If it's a GitHub URL, ensure .git suffix
    if "github.com" in url and not url.endswith(".git"):
        return f"{url}.git"

    # Pass through all other URLs unchanged
    return url


def extract_repo_name_from_url(url: str) -> str:
    """Extract the repository name from a git URL.

    Args:
        url: A git URL (HTTPS, SSH, or GitHub shorthand).

    Returns:
        The repository name without the .git suffix.

    Examples:
        "https://github.com/griptape-ai/griptape-nodes-library-advanced" -> "griptape-nodes-library-advanced"
        "https://github.com/griptape-ai/griptape-nodes-library-advanced.git" -> "griptape-nodes-library-advanced"
        "git@github.com:user/repo.git" -> "repo"
        "griptape-ai/repo" -> "repo"
    """
    url = url.strip().rstrip("/")

    # Remove .git suffix if present
    url = url.removesuffix(".git")

    # Extract the last part of the path
    # Handle both https://domain/owner/repo and git@domain:owner/repo formats
    if ":" in url and not url.startswith(("http://", "https://", "ssh://")):
        # SSH format: git@github.com:owner/repo
        repo_name = url.split(":")[-1].split("/")[-1]
    else:
        # HTTPS format or shorthand: https://github.com/owner/repo or owner/repo
        repo_name = url.split("/")[-1]

    return repo_name


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
        raise GitRemoteError(msg) from e


def get_current_ref(library_path: Path) -> str | None:
    """Get the current git reference (branch, tag, or commit) for a library directory.

    Args:
        library_path: The path to the library directory.

    Returns:
        str | None: The current git reference if found, None if not a git repository or detached HEAD.

    Raises:
        GitRefError: If an error occurs while getting the current git reference.
    """
    if not is_git_repository(library_path):
        logger.debug("Path %s is not a git repository", library_path)
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            logger.debug("Could not discover git repository at %s", library_path)
            return None

        repo = pygit2.Repository(repo_path)

        # Check if HEAD is detached
        if repo.head_is_detached:
            # HEAD is detached - check if it's pointing to a tag
            tag_name = get_current_tag(library_path)
            if tag_name:
                logger.debug("Repository at %s has detached HEAD on tag %s", library_path, tag_name)
                return tag_name

            logger.debug("Repository at %s has detached HEAD (not on a tag)", library_path)
            return None

    except pygit2.GitError as e:
        msg = f"Error getting current git reference for {library_path}: {e}"
        raise GitRefError(msg) from e
    else:
        # Get the current git reference name (branch)
        return repo.head.shorthand


def get_current_tag(library_path: Path) -> str | None:
    """Get the current tag name if HEAD is pointing to a tag.

    Args:
        library_path: The path to the library directory.

    Returns:
        str | None: The current tag name if found, None if not on a tag or not a git repository.

    Raises:
        GitError: If an error occurs while getting the current tag.
    """
    if not is_git_repository(library_path):
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            return None

        repo = pygit2.Repository(repo_path)

        # Get the current HEAD commit
        if repo.head_is_unborn:
            return None

        head_commit = repo.head.target

        # Check all tags to see if any point to HEAD
        for tag_name in repo.references:
            if not tag_name.startswith("refs/tags/"):
                continue

            tag_ref = repo.references[tag_name]
            # Handle both lightweight and annotated tags
            if hasattr(tag_ref, "peel"):
                tag_target = tag_ref.peel(pygit2.Commit).id
            else:
                tag_target = tag_ref.target

            if tag_target == head_commit:
                # Return tag name without refs/tags/ prefix
                return tag_name.replace("refs/tags/", "")
    except pygit2.GitError as e:
        msg = f"Error getting current tag for {library_path}: {e}"
        raise GitError(msg) from e
    else:
        return None


def is_on_tag(library_path: Path) -> bool:
    """Check if HEAD is currently pointing to a tag.

    Args:
        library_path: The path to the library directory.

    Returns:
        bool: True if HEAD is on a tag, False otherwise.
    """
    return get_current_tag(library_path) is not None


def get_local_commit_sha(library_path: Path) -> str | None:
    """Get the current HEAD commit SHA for a library directory.

    Args:
        library_path: The path to the library directory.

    Returns:
        str | None: The full commit SHA if found, None if not a git repository or error occurs.

    Raises:
        GitError: If an error occurs while getting the commit SHA.
    """
    if not is_git_repository(library_path):
        return None

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            return None

        repo = pygit2.Repository(repo_path)

        if repo.head_is_unborn:
            return None

        return str(repo.head.target)

    except pygit2.GitError as e:
        msg = f"Error getting commit SHA for {library_path}: {e}"
        raise GitError(msg) from e


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
        raise GitRepositoryError(msg) from e
    else:
        # Normal repository - return parent of .git directory
        return git_dir.parent


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
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Check for detached HEAD
        if repo.head_is_detached:
            msg = f"Repository at {library_path} has detached HEAD"
            raise GitPullError(msg)

        # Get the current branch
        current_branch = repo.branches.get(repo.head.shorthand)
        if current_branch is None:
            msg = f"Cannot get current branch for repository at {library_path}"
            raise GitPullError(msg)

        # Check for upstream
        upstream = current_branch.upstream
        if upstream is None:
            msg = f"No upstream branch set for {current_branch.branch_name} at {library_path}"
            raise GitPullError(msg)

        # Check for origin remote
        try:
            _ = repo.remotes["origin"]
        except (KeyError, IndexError) as e:
            msg = f"No origin remote found for repository at {library_path}"
            raise GitPullError(msg) from e

    except pygit2.GitError as e:
        msg = f"Git error during pull --rebase at {library_path}: {e}"
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
            raise GitPullError(msg)

    except subprocess.SubprocessError as e:
        msg = f"Subprocess error during pull --rebase at {library_path}: {e}"
        raise GitPullError(msg) from e


def update_to_moving_tag(library_path: Path, tag_name: str) -> None:
    """Update library to the latest version of a moving tag.

    This function is designed for tags that are force-pushed to point to new commits
    (e.g., a 'latest' tag that always points to the newest release).

    Args:
        library_path: The path to the library directory.
        tag_name: The name of the tag to update to (e.g., "latest").

    Raises:
        GitRepositoryError: If the path is not a valid git repository.
        GitPullError: If the tag update operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot update tag: {library_path} is not a git repository"
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Check for origin remote
        try:
            _ = repo.remotes["origin"]
        except (KeyError, IndexError) as e:
            msg = f"No origin remote found for repository at {library_path}"
            raise GitPullError(msg) from e

    except pygit2.GitError as e:
        msg = f"Git error during tag update at {library_path}: {e}"
        raise GitPullError(msg) from e

    # Use subprocess to fetch tags and checkout
    try:
        # Step 1: Fetch all tags, force update existing ones
        fetch_result = subprocess.run(
            ["git", "fetch", "--tags", "--force", "origin"],  # noqa: S607
            cwd=str(library_path),
            capture_output=True,
            text=True,
            check=False,
        )

        if fetch_result.returncode != 0:
            msg = f"Git fetch --tags --force failed at {library_path}: {fetch_result.stderr}"
            raise GitPullError(msg)

        # Step 2: Checkout the tag (this will put us in detached HEAD state, which is expected)
        checkout_result = subprocess.run(  # noqa: S603
            ["git", "checkout", f"tags/{tag_name}"],  # noqa: S607
            cwd=str(library_path),
            capture_output=True,
            text=True,
            check=False,
        )

        if checkout_result.returncode != 0:
            msg = f"Git checkout tags/{tag_name} failed at {library_path}: {checkout_result.stderr}"
            raise GitPullError(msg)

    except subprocess.SubprocessError as e:
        msg = f"Subprocess error during tag update at {library_path}: {e}"
        raise GitPullError(msg) from e


def update_library_git(library_path: Path) -> None:
    """Update a library to the latest version using the appropriate git strategy.

    This function automatically detects whether the library uses a branch-based or
    tag-based workflow and applies the correct update mechanism:
    - Branch-based: Uses git pull --rebase
    - Tag-based: Uses git fetch --tags --force + git checkout

    Args:
        library_path: The path to the library directory.

    Raises:
        GitRepositoryError: If the path is not a valid git repository.
        GitPullError: If the update operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot update: {library_path} is not a git repository"
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Detect workflow type
        if repo.head_is_detached:
            # Detached HEAD - likely on a tag
            tag_name = get_current_tag(library_path)
            if tag_name is None:
                msg = f"Repository at {library_path} is in detached HEAD state but not on a known tag. Cannot auto-update."
                raise GitPullError(msg)

            logger.debug("Detected tag-based workflow for %s (tag: %s)", library_path, tag_name)
            update_to_moving_tag(library_path, tag_name)
        else:
            # On a branch - use standard pull --rebase
            logger.debug("Detected branch-based workflow for %s", library_path)
            git_pull_rebase(library_path)

    except pygit2.GitError as e:
        msg = f"Git error during library update at {library_path}: {e}"
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
        GitRefError: If the branch switch operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot switch branch: {library_path} is not a git repository"
        raise GitRepositoryError(msg)

    try:
        repo_path = pygit2.discover_repository(str(library_path))
        if repo_path is None:
            msg = f"Cannot discover repository at {library_path}"
            raise GitRepositoryError(msg)

        repo = pygit2.Repository(repo_path)

        # Get origin remote
        try:
            remote = repo.remotes["origin"]
        except (KeyError, IndexError) as e:
            msg = f"No origin remote found for repository at {library_path}"
            raise GitRefError(msg) from e

        # Fetch from remote first
        remote.fetch()

        # Try to find the branch locally first
        local_branch = repo.branches.get(branch_name)

        if local_branch is not None:
            # Branch exists locally, just check it out
            repo.checkout(local_branch)
            logger.debug("Checked out existing local branch %s at %s", branch_name, library_path)
            return

        # Branch doesn't exist locally, try to find it on remote
        remote_branch_name = f"origin/{branch_name}"
        remote_branch = repo.branches.get(remote_branch_name)

        if remote_branch is None:
            msg = f"Branch {branch_name} not found locally or on remote at {library_path}"
            raise GitRefError(msg)

        # Create local tracking branch from remote
        commit = repo.get(remote_branch.target)
        if commit is None:
            msg = f"Failed to get commit for remote branch {remote_branch_name} at {library_path}"
            raise GitRefError(msg)

        new_branch = repo.branches.local.create(branch_name, commit)  # type: ignore[arg-type]
        new_branch.upstream = remote_branch

        # Checkout the new branch
        repo.checkout(new_branch)
        logger.debug(
            "Created and checked out tracking branch %s from %s at %s", branch_name, remote_branch_name, library_path
        )

    except pygit2.GitError as e:
        msg = f"Git error during branch switch at {library_path}: {e}"
        raise GitRefError(msg) from e


def switch_branch_or_tag(library_path: Path, ref_name: str) -> None:
    """Switch to a different branch or tag in a library directory.

    Fetches from remote first, then checks out the specified branch or tag.
    Automatically detects whether the ref is a branch or tag.

    Args:
        library_path: The path to the library directory.
        ref_name: The name of the branch or tag to switch to.

    Raises:
        GitRepositoryError: If the path is not a valid git repository.
        GitRefError: If the switch operation fails.
    """
    if not is_git_repository(library_path):
        msg = f"Cannot switch ref: {library_path} is not a git repository"
        raise GitRepositoryError(msg)

    try:
        # Use subprocess for fetching to get both branches and tags
        fetch_result = subprocess.run(
            ["git", "fetch", "--tags", "origin"],  # noqa: S607
            cwd=str(library_path),
            capture_output=True,
            text=True,
            check=False,
        )

        if fetch_result.returncode != 0:
            msg = f"Git fetch failed at {library_path}: {fetch_result.stderr}"
            raise GitRefError(msg)

        # Try to checkout the ref (works for both branches and tags)
        checkout_result = subprocess.run(  # noqa: S603
            ["git", "checkout", ref_name],  # noqa: S607
            cwd=str(library_path),
            capture_output=True,
            text=True,
            check=False,
        )

        if checkout_result.returncode != 0:
            msg = f"Git checkout {ref_name} failed at {library_path}: {checkout_result.stderr}"
            raise GitRefError(msg)

        logger.debug("Checked out %s at %s", ref_name, library_path)

    except subprocess.SubprocessError as e:
        msg = f"Subprocess error during ref switch at {library_path}: {e}"
        raise GitRefError(msg) from e


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


def clone_repository(git_url: str, target_path: Path, branch_tag_commit: str | None = None) -> None:
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
        raise GitCloneError(msg)

    # Convert SSH URLs to HTTPS for compatibility
    original_url = git_url
    if _is_ssh_url(git_url):
        git_url = _convert_ssh_to_https(git_url)
        logger.debug("Converted SSH URL to HTTPS: %s -> %s", original_url, git_url)

    try:
        # Clone the repository
        repo = pygit2.clone_repository(git_url, str(target_path))
        if repo is None:
            msg = f"Failed to clone repository from {git_url}"
            raise GitCloneError(msg)

        # Checkout specific branch/tag/commit if provided
        if branch_tag_commit:
            # Try to resolve as a branch first
            try:
                branch = repo.branches[branch_tag_commit]
                repo.checkout(branch)
                logger.debug("Checked out branch %s", branch_tag_commit)
            except (pygit2.GitError, KeyError, IndexError):
                # Try to resolve as a tag or commit
                try:
                    commit_obj = repo.revparse_single(branch_tag_commit)
                    repo.checkout_tree(commit_obj)
                    repo.set_head(commit_obj.id)
                    logger.debug("Checked out %s", branch_tag_commit)
                except pygit2.GitError as e:
                    msg = f"Failed to checkout {branch_tag_commit}: {e}"
                    raise GitCloneError(msg) from e

    except pygit2.GitError as e:
        msg = f"Git error while cloning {git_url} to {target_path}: {e}"
        raise GitCloneError(msg) from e
