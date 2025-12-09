"""Utility functions for validating artifact accessibility when loading flows.

This module provides functions to check if ImageUrlArtifact and VideoUrlArtifact
URLs are accessible (either as HTTP(S) URLs or local file paths). Used during
flow loading to identify inaccessible artifacts and unresolve affected nodes.
"""

from pathlib import Path
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact, VideoUrlArtifact


def default_extract_url_from_artifact_value(
    artifact_value: Any, artifact_classes: type | tuple[type, ...]
) -> str | None:
    """Default implementation to extract URL from any artifact parameter value.

    This function provides the standard pattern for extracting URLs from artifact values
    that can be in dict, artifact object, or string format. Users can override this
    behavior by providing their own extract_url_func in ArtifactTetheringConfig.

    Args:
        artifact_value: The artifact value (dict, artifact object, or string)
        artifact_classes: The artifact class(es) to check for (e.g., ImageUrlArtifact, VideoUrlArtifact)

    Returns:
        The extracted URL or None if no value is present

    Raises:
        ValueError: If the artifact value type is not supported
    """
    if not artifact_value:
        return None

    match artifact_value:
        # Handle dictionary format (most common)
        case dict():
            url = artifact_value.get("value")
        # Handle artifact objects - use isinstance for type safety
        case _ if isinstance(artifact_value, artifact_classes):
            url = artifact_value.value
        # Handle raw strings
        case str():
            url = artifact_value
        case _:
            # Generate error message with expected class names
            if isinstance(artifact_classes, tuple):
                class_names = [cls.__name__ for cls in artifact_classes]
            else:
                class_names = [artifact_classes.__name__]

            expected_types = f"dict, {', '.join(class_names)}, or str"
            error_msg = f"Unsupported artifact value type: {type(artifact_value).__name__}. Expected: {expected_types}"
            raise ValueError(error_msg)

    if not url:
        return None

    return url


def check_url_accessibility(url: str, timeout: int = 5) -> bool:
    """Check if an HTTP(S) URL is accessible.

    Uses HEAD request (lightweight, doesn't download content) to verify URL accessibility.

    Args:
        url: The HTTP or HTTPS URL to check
        timeout: Timeout in seconds for the request (default: 5)

    Returns:
        True if URL is accessible (status 200-299), False otherwise
    """
    try:
        response = httpx.head(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        return False
    except httpx.RequestError:
        return False
    else:
        return True


def check_file_accessibility(file_path: str, workspace_path: Path) -> bool:
    """Check if a local file path exists and is readable.

    Handles both absolute and workspace-relative paths.

    Args:
        file_path: The file path to check (absolute or relative)
        workspace_path: The workspace root path for resolving relative paths

    Returns:
        True if file exists and is a file, False otherwise
    """
    if not file_path:
        return False

    path = Path(file_path)

    if not path.is_absolute():
        path = workspace_path / path

    if not path.exists():
        return False

    return path.is_file()


def is_artifact_accessible(artifact_value: Any, artifact_classes: tuple[type, ...], workspace_path: Path) -> bool:
    """Check if an artifact value's URL/path is accessible.

    Extracts URL from artifact value and checks accessibility based on URL type
    (HTTP(S) URL or local file path).

    Args:
        artifact_value: The artifact value (dict, artifact object, or string)
        artifact_classes: The artifact class(es) to check for (e.g., ImageUrlArtifact, VideoUrlArtifact)
        workspace_path: The workspace root path for resolving relative file paths

    Returns:
        True if artifact is accessible, False if not or if URL is None/empty
    """
    if not artifact_value:
        return False

    url = default_extract_url_from_artifact_value(artifact_value, artifact_classes)

    if not url:
        return False

    if url.startswith(("http://", "https://")):
        return check_url_accessibility(url)

    return check_file_accessibility(url, workspace_path)


def is_image_or_video_url_artifact(value: Any) -> bool:
    """Check if value is an ImageUrlArtifact or VideoUrlArtifact.

    Args:
        value: The value to check

    Returns:
        True if value is ImageUrlArtifact or VideoUrlArtifact (instance or dict), False otherwise
    """
    if not value:
        return False

    # Check if value is ImageUrlArtifact or VideoUrlArtifact instance
    if isinstance(value, (ImageUrlArtifact, VideoUrlArtifact)):
        return True

    # Check if value is a dict with type field indicating ImageUrlArtifact or VideoUrlArtifact
    if isinstance(value, dict):
        artifact_type = value.get("type", "")
        if artifact_type in ("ImageUrlArtifact", "VideoUrlArtifact"):
            return True

    return False
