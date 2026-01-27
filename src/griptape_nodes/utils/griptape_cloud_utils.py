"""Utilities for working with Griptape Cloud asset URLs."""

import logging
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("griptape_nodes")


def is_cloud_asset_url(url_str: str) -> bool:
    """Check if URL is a Griptape Cloud asset URL with domain validation.

    Detects URLs matching pattern: https://cloud.griptape.ai/buckets/{id}/assets/{path}
    Validates domain matches expected cloud domain (default: cloud.griptape.ai).

    Args:
        url_str: String to check

    Returns:
        True if url_str is a valid cloud asset URL
    """
    # Fast negative checks first
    if not url_str:
        return False

    # Must be a full URL with scheme
    if not url_str.startswith(("http://", "https://")):
        return False

    # Parse URL to check domain
    parsed = urlparse(url_str)
    domain = parsed.netloc.lower()

    # Get expected cloud domain from environment
    base_url = os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
    expected_parsed = urlparse(base_url)
    expected_domain = expected_parsed.netloc.lower()

    # Domain must match
    if domain != expected_domain:
        return False

    # Must contain both /buckets/ and /assets/ patterns
    path = parsed.path
    has_buckets = "/buckets/" in path
    has_assets = "/assets/" in path

    # Success path - valid cloud asset URL
    return has_buckets and has_assets


def extract_workspace_path_from_cloud_url(url_str: str) -> str | None:
    """Extract workspace-relative path from cloud asset URL.

    Parses URLs like: /buckets/{bucket_id}/assets/{workspace_path}
    Returns just the {workspace_path} portion.

    Args:
        url_str: Cloud asset URL

    Returns:
        Workspace-relative path, or None if parsing fails
    """
    parsed = urlparse(url_str)
    path = parsed.path

    # Extract workspace-relative path from: /buckets/{bucket_id}/assets/{workspace_path}
    expected_parts = 2
    try:
        parts = path.split("/assets/", 1)
        if len(parts) != expected_parts:
            return None
        return parts[1]
    except Exception:
        return None


def create_signed_download_url(asset_url: str, *, httpx_request_func: Callable[..., Any]) -> str | None:
    """Create a signed download URL for a cloud asset.

    Args:
        asset_url: Cloud asset URL to convert
        httpx_request_func: The httpx request function to use (should be original, not patched)

    Returns:
        Signed download URL if successful, None if fails
    """
    # Guard: Check for required credentials
    bucket_id = os.environ.get("GT_CLOUD_BUCKET_ID")
    api_key = os.environ.get("GT_CLOUD_API_KEY")

    if not bucket_id:
        logger.debug("GT_CLOUD_BUCKET_ID not set, skipping cloud URL conversion: %s", asset_url)
        return None

    if not api_key:
        logger.debug("GT_CLOUD_API_KEY not set, skipping cloud URL conversion: %s", asset_url)
        return None

    # Extract workspace-relative path
    workspace_path = extract_workspace_path_from_cloud_url(asset_url)
    if not workspace_path:
        logger.debug("Could not extract workspace path from cloud URL: %s", asset_url)
        return None

    # Build API URL for signed download URL
    base_url = os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
    api_url = urljoin(base_url, f"/api/buckets/{bucket_id}/asset-urls/{workspace_path}")

    # Make API request to get signed URL
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = httpx_request_func("POST", api_url, json={"method": "GET"}, headers=headers)
        response.raise_for_status()

        response_data = response.json()
        signed_url = response_data["url"]

        logger.info("Converted cloud asset URL to signed URL: %s", asset_url)
    except Exception as e:
        if isinstance(e, httpx.HTTPStatusError):
            logger.warning("Failed to create signed download URL for %s: HTTP %s", asset_url, e.response.status_code)
        else:
            logger.warning("Failed to create signed download URL for %s: %s", asset_url, e)
        return None
    else:
        return signed_url
