"""Core utilities for normalizing artifact inputs (images, videos, audio).

This module provides normalization functions that convert string paths to
their respective artifact types (ImageUrlArtifact, VideoUrlArtifact, AudioUrlArtifact).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


def _resolve_localhost_url_to_path(url: str) -> str:
    """Resolve localhost static file URLs to workspace file paths.

    Converts URLs like http://localhost:8124/workspace/static_files/file.jpg
    to actual workspace file paths like static_files/file.jpg

    Args:
        url: URL string that may be a localhost URL

    Returns:
        Resolved file path relative to workspace, or original string if not a localhost URL
    """
    if not isinstance(url, str):
        return url

    # Strip query parameters (cachebuster ?t=...)
    if "?" in url:
        url = url.split("?")[0]

    # Check if it's a localhost URL (any port)
    if url.startswith(("http://localhost:", "https://localhost:")):
        parsed = urlparse(url)
        # Extract path after /workspace/
        if "/workspace/" in parsed.path:
            workspace_relative_path = parsed.path.split("/workspace/", 1)[1]
            return workspace_relative_path

    # Not a localhost workspace URL, return as-is
    return url


def _resolve_file_path(file_path: str) -> Path | None:
    """Resolve file path to absolute path relative to workspace.

    Args:
        file_path: File path (may be absolute, relative, or localhost URL)

    Returns:
        Resolved Path object, or None if path cannot be resolved
    """
    # First resolve localhost URLs
    file_path = _resolve_localhost_url_to_path(file_path)

    try:
        path = Path(file_path)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if path.is_absolute():
            # Check if absolute path is relative to workspace
            try:
                if path.is_relative_to(workspace_path):
                    return path
            except (ValueError, AttributeError):
                # Path.is_relative_to() not available in older Python versions
                try:
                    path.relative_to(workspace_path)
                except ValueError:
                    # Absolute path outside workspace - return as-is (might be a system path)
                    return path if path.exists() else None
                else:
                    return path
            # Absolute path outside workspace - return as-is (might be a system path)
            return path if path.exists() else None
        # Relative path - resolve relative to workspace
        return workspace_path / path
    except Exception as e:
        logger.debug("Failed to resolve file path '%s': %s", file_path, e)
        return None


def _upload_file_to_static_storage(file_path: Path, artifact_type: type[Any]) -> Any | None:
    """Upload a file to static storage and return an artifact.

    Args:
        file_path: Path to the file to upload
        artifact_type: The artifact class to create (ImageUrlArtifact, VideoUrlArtifact, AudioUrlArtifact)

    Returns:
        Artifact object with localhost URL, or None if upload fails
    """
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        file_data = file_path.read_bytes()
        file_name = file_path.name
        static_files_manager = GriptapeNodes.StaticFilesManager()
        url = static_files_manager.save_static_file(file_data, file_name)
        return artifact_type(url)
    except Exception as e:
        logger.debug("Failed to upload file '%s' to static storage: %s", file_path, e)
        return None


def _normalize_string_input(artifact_input: str, artifact_type: type[Any]) -> Any:
    """Normalize a string input to an artifact.

    Args:
        artifact_input: String input (URL or file path)
        artifact_type: The artifact class to create

    Returns:
        Artifact object or original input if normalization fails
    """
    # If it's already a URL (http/https), return it as-is
    if artifact_input.startswith(("http://", "https://")):
        # Check if it's a localhost URL that needs resolving
        if artifact_input.startswith(("http://localhost:", "https://localhost:")):
            resolved_path = _resolve_localhost_url_to_path(artifact_input)
            if resolved_path != artifact_input:
                # It was a localhost URL, try to resolve and upload
                file_path = _resolve_file_path(resolved_path)
                if file_path:
                    artifact = _upload_file_to_static_storage(file_path, artifact_type)
                    if artifact:
                        return artifact
            # If resolution failed, return as URL artifact
            return artifact_type(artifact_input)
        # Regular URL, return as-is
        return artifact_type(artifact_input)

    # Try to resolve and upload file path
    file_path = _resolve_file_path(artifact_input)
    if file_path:
        artifact = _upload_file_to_static_storage(file_path, artifact_type)
        if artifact:
            return artifact

    return artifact_input


def normalize_artifact_input(
    artifact_input: Any,
    artifact_type: type[Any],
    *,
    accepted_types: tuple[type[Any], ...] | None = None,
) -> Any:
    """Normalize an artifact input, converting string paths to the specified artifact type.

    This ensures consistency whether values come from user input or node connections.
    String paths are uploaded to static storage and converted to artifact objects.
    Objects that are already the correct artifact type are returned unchanged.

    Args:
        artifact_input: Artifact input (may be string, artifact object, etc.)
        artifact_type: The artifact class to create (ImageUrlArtifact, VideoUrlArtifact, AudioUrlArtifact)
        accepted_types: Optional tuple of artifact types that should be passed through unchanged.
            For example, for images, both ImageUrlArtifact and ImageArtifact are valid.

    Returns:
        Artifact of the specified type if input was a string path, otherwise returns input unchanged
    """
    # Return unchanged if already the correct artifact type
    if isinstance(artifact_input, artifact_type):
        return artifact_input

    # Also return unchanged if it's one of the accepted types (e.g., ImageArtifact for images)
    if accepted_types and isinstance(artifact_input, accepted_types):
        return artifact_input

    # Process string paths
    if isinstance(artifact_input, str) and artifact_input:
        return _normalize_string_input(artifact_input, artifact_type)

    return artifact_input


def normalize_artifact_list(
    artifact_list: list[Any],
    artifact_type: type[Any],
    *,
    accepted_types: tuple[type[Any], ...] | None = None,
) -> list[Any]:
    """Normalize a list of artifact inputs, converting string paths to the specified artifact type.

    This ensures consistency whether values come from user input or node connections.
    String paths are uploaded to static storage and converted to artifact objects.
    Objects that are already the correct artifact type are passed through unchanged.

    Args:
        artifact_list: List of artifact inputs (may contain strings, artifact objects, etc.)
        artifact_type: The artifact class to create (ImageUrlArtifact, VideoUrlArtifact, AudioUrlArtifact)
        accepted_types: Optional tuple of artifact types that should be passed through unchanged.
            For example, for images, both ImageUrlArtifact and ImageArtifact are valid.

    Returns:
        List with string paths converted to artifacts of the specified type
    """
    if not artifact_list:
        return artifact_list

    return [normalize_artifact_input(item, artifact_type, accepted_types=accepted_types) for item in artifact_list]


__all__ = ["normalize_artifact_input", "normalize_artifact_list"]
