"""Version utilities for Griptape Nodes."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Literal

from rich.console import Console

console = Console()

engine_version = importlib.metadata.version("griptape_nodes")


def get_current_version() -> str:
    """Returns the current version of the Griptape Nodes package."""
    return f"v{engine_version}"


def get_install_source() -> tuple[Literal["git", "file", "pypi", "unknown"], str | None]:
    """Determines the install source of the Griptape Nodes package.

    Searches for the dist-info in the same site-packages directory as the
    running code to correctly identify the source when multiple installations
    of the package exist across different environments on sys.path.

    Returns:
        tuple: A tuple containing the install source and commit ID (if applicable).
    """
    # Search for the dist-info in the same directory as this running module
    # (i.e., the site-packages containing the code that is actually executing).
    # This avoids picking up a different installation that appears earlier in
    # sys.path when multiple environments coexist (e.g., a uv tool install
    # alongside a local project install).
    code_site_packages = next(
        (p for p in Path(__file__).parents if p.name == "site-packages"),
        None,
    )
    dist = None
    if code_site_packages is not None:
        dist = next(
            (
                d
                for d in importlib.metadata.distributions(path=[str(code_site_packages)])
                if d.metadata.get("Name", "").lower() in ("griptape-nodes", "griptape_nodes")
            ),
            None,
        )

    # Fall back for editable installs where __file__ is in the source tree
    # rather than site-packages, so the dist-info won't be found above.
    if dist is None:
        try:
            dist = importlib.metadata.distribution("griptape_nodes")
        except importlib.metadata.PackageNotFoundError:
            return "unknown", None

    direct_url_text = dist.read_text("direct_url.json")
    # installing from pypi doesn't have a direct_url.json file
    if direct_url_text is None:
        return "pypi", None

    direct_url_info = json.loads(direct_url_text)
    url = direct_url_info.get("url")
    if url and url.startswith("file://"):
        return "file", None
    if "vcs_info" in direct_url_info:
        commit_id = direct_url_info["vcs_info"].get("commit_id")
        return "git", commit_id[:7] if commit_id else None
    # direct_url.json exists but matches no known pattern (e.g., direct HTTP tarball)
    return "unknown", None


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
