"""Utility functions for string manipulation."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


def derive_registry_key(file_path: str) -> str:
    """Derive a workflow registry key from a file path.

    Strips the file extension and normalizes directory separators to forward slashes,
    preserving directory components for uniqueness across different directories.

    Args:
        file_path: Path to the workflow file, e.g. "subdir/my_workflow.py"

    Returns:
        Registry key with directory components preserved, e.g. "subdir/my_workflow"

    Examples:
        >>> derive_registry_key("my_workflow.py")
        "my_workflow"
        >>> derive_registry_key("subdir/my_workflow.py")
        "subdir/my_workflow"
    """
    normalized = file_path.replace("\\", "/")
    return str(PurePosixPath(normalized).with_suffix(""))


def normalize_display_name(name: str) -> str:
    """Normalize a human-readable display name to a safe lowercase identifier.

    Lowercases, trims whitespace, replaces non-alphanumeric/hyphen characters
    with a space, then collapses spaces into underscores.

    Args:
        name: Human-readable name, e.g. "My Cool Workflow!" or "Standard Thumbnail Generation"

    Returns:
        A lowercase, underscore-separated identifier suitable for use as a
        config key or file stem, e.g. "my_cool_workflow" or "standard_thumbnail_generation"

    Examples:
        >>> normalize_display_name("My Cool Workflow!")
        "my_cool_workflow"
        >>> normalize_display_name("  Hello World  ")
        "hello_world"
        >>> normalize_display_name("Standard Thumbnail Generation")
        "standard_thumbnail_generation"
        >>> normalize_display_name("Image")
        "image"
    """
    normalized = name.strip().lower()
    normalized = re.sub(r"[^a-z0-9-]", " ", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized
