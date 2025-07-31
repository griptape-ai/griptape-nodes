"""Version utilities for Griptape Nodes."""

from __future__ import annotations

import importlib.metadata
import json
from typing import Literal

engine_version = importlib.metadata.version("griptape_nodes")


def get_current_version() -> str:
    """Returns the current version of the Griptape Nodes package."""
    return f"v{engine_version}"


def get_install_source() -> tuple[Literal["git", "file", "pypi"], str | None]:
    """Determines the install source of the Griptape Nodes package.

    Returns:
        tuple: A tuple containing the install source and commit ID (if applicable).
    """
    dist = importlib.metadata.distribution("griptape_nodes")
    direct_url_text = dist.read_text("direct_url.json")
    # installing from pypi doesn't have a direct_url.json file
    if direct_url_text is None:
        return "pypi", None

    direct_url_info = json.loads(direct_url_text)
    url = direct_url_info.get("url")
    if url and url.startswith("file://"):
        return "file", None
    if "vcs_info" in direct_url_info:
        return "git", direct_url_info["vcs_info"].get("commit_id")[:7]
    # Fall back to pypi if no other source is found
    return "pypi", None


def get_complete_version_string() -> str:
    """Returns the complete version string including install source and commit ID.

    Format: v1.2.3 (source) or v1.2.3 (source - commit_id)

    Returns:
        Complete version string with source and commit info.
    """
    version = get_current_version()
    source, commit_id = get_install_source()
    if commit_id is None:
        return f"{version} ({source})"
    return f"{version} ({source} - {commit_id})"
