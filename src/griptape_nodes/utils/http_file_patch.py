r"""Monkey-patch httpx and requests to transparently handle file:// URLs and local file paths.

This module patches httpx and requests libraries at runtime to support:
- file:// URLs
- Absolute local file paths (e.g., /path/to/file.txt, C:\path\to\file.txt)
- Network paths (UNC paths like \\server\share\file.txt, if accessible)

File operations are mapped to HTTP-like responses for seamless integration with
existing code. HTTP/HTTPS/FTP URLs are fast-pathed to avoid filesystem checks.
"""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx
import requests

from griptape_nodes.utils.url_utils import get_content_type_from_extension

logger = logging.getLogger("griptape_nodes")

# HTTP status code constants
HTTP_OK = 200
HTTP_MULTIPLE_CHOICES = 300
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_ERROR_THRESHOLD = 600

# Store original functions to delegate non-file:// URLs
_original_httpx_request: Any = None
_original_httpx_get: Any = None
_original_httpx_post: Any = None
_original_httpx_put: Any = None
_original_httpx_delete: Any = None
_original_httpx_patch: Any = None
_original_requests_get: Any = None

_patches_installed = False


def _is_http_url(url_str: str) -> bool:
    """Quick check for http/https/ftp URLs to bypass filesystem checks."""
    return url_str.startswith(("http://", "https://", "ftp://", "ftps://"))


def _is_local_file_path(url_str: str) -> bool:
    """Check if string is an absolute file path that exists.

    Excludes URLs that already have schemes (file://, http://, etc.).
    Network paths (UNC) are allowed if they exist and are accessible.

    Args:
        url_str: String to check

    Returns:
        True if url_str is an absolute file path that exists
    """
    # Exclude URLs with schemes - handle them via existing logic
    if "://" in url_str:
        return False

    # Check if absolute path that exists
    try:
        path = Path(url_str)
        return path.is_absolute() and path.exists()
    except (ValueError, OSError):
        return False


class FileHttpxResponse:
    """Response wrapper that mimics httpx.Response interface for file:// URLs."""

    def __init__(self, content: bytes, status_code: int, file_path: str):
        """Initialize file response.

        Args:
            content: File content as bytes
            status_code: HTTP status code (200 for success, 404/403/etc for errors)
            file_path: Path to the file for MIME type detection
        """
        self.content = content
        self.status_code = status_code
        self._file_path = file_path

        # Build headers dict
        headers_dict = {}
        if status_code == HTTP_OK:
            headers_dict["Content-Length"] = str(len(content))
            content_type = get_content_type_from_extension(file_path)
            if content_type:
                headers_dict["Content-Type"] = content_type

        self.headers = headers_dict

    @property
    def text(self) -> str:
        """Return content as text string."""
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        """Raise HTTPStatusError for error status codes (4xx, 5xx)."""
        if HTTP_BAD_REQUEST <= self.status_code < HTTP_ERROR_THRESHOLD:
            msg = f"File error: {self.status_code} for file:// URL: {self._file_path}"
            # Create a minimal request object for the exception
            request = httpx.Request("GET", self._file_path)
            raise httpx.HTTPStatusError(msg, request=request, response=self)  # type: ignore[arg-type]

    def json(self) -> Any:
        """Parse content as JSON."""
        import json

        return json.loads(self.text)


class FileRequestsResponse:
    """Response wrapper that mimics requests.Response interface for file:// URLs."""

    def __init__(self, content: bytes, status_code: int, file_path: str):
        """Initialize file response.

        Args:
            content: File content as bytes
            status_code: HTTP status code (200 for success, 404/403/etc for errors)
            file_path: Path to the file for MIME type detection
        """
        self.content = content
        self.status_code = status_code
        self._file_path = file_path

        # Build headers dict
        headers_dict = {}
        if status_code == HTTP_OK:
            headers_dict["Content-Length"] = str(len(content))
            content_type = get_content_type_from_extension(file_path)
            if content_type:
                headers_dict["Content-Type"] = content_type

        self.headers = headers_dict
        self.ok = HTTP_OK <= status_code < HTTP_MULTIPLE_CHOICES

    @property
    def text(self) -> str:
        """Return content as text string."""
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        """Raise HTTPError for error status codes (4xx, 5xx)."""
        if HTTP_BAD_REQUEST <= self.status_code < HTTP_ERROR_THRESHOLD:
            msg = f"File error: {self.status_code} for file:// URL: {self._file_path}"
            raise requests.HTTPError(msg, response=self)  # type: ignore[arg-type]

    def json(self) -> Any:
        """Parse content as JSON."""
        import json

        return json.loads(self.text)


def _handle_file_url(url: str, *, response_type: type) -> FileHttpxResponse | FileRequestsResponse:
    """Handle file:// URL by reading local file and returning HTTP-like response.

    Args:
        url: file:// URL to handle
        response_type: Response class to instantiate (FileHttpxResponse or FileRequestsResponse)

    Returns:
        Response wrapper with file content or error status
    """
    # Validate input
    if not url.startswith("file://"):
        return response_type(
            content=b"",
            status_code=HTTP_BAD_REQUEST,
            file_path=url,
        )

    # Extract file path from file:// URL (same pattern as static_files_manager.py:193-196)
    parsed = urlparse(url)
    file_path_str = url2pathname(parsed.path)
    file_path = Path(file_path_str)

    # Check if file exists
    if not file_path.exists():
        error_msg = f"File not found: {file_path_str}"
        logger.debug(error_msg)
        return response_type(
            content=error_msg.encode("utf-8"),
            status_code=HTTP_NOT_FOUND,
            file_path=file_path_str,
        )

    # Check if path is a directory
    if file_path.is_dir():
        error_msg = f"Path is a directory, not a file: {file_path_str}"
        logger.debug(error_msg)
        return response_type(
            content=error_msg.encode("utf-8"),
            status_code=HTTP_BAD_REQUEST,
            file_path=file_path_str,
        )

    # Try to read file
    try:
        content = file_path.read_bytes()
    except PermissionError:
        error_msg = f"Permission denied: {file_path_str}"
        logger.debug(error_msg)
        return response_type(
            content=error_msg.encode("utf-8"),
            status_code=HTTP_FORBIDDEN,
            file_path=file_path_str,
        )
    except OSError as e:
        error_msg = f"Error reading file: {file_path_str}: {e}"
        logger.debug(error_msg)
        return response_type(
            content=error_msg.encode("utf-8"),
            status_code=HTTP_INTERNAL_SERVER_ERROR,
            file_path=file_path_str,
        )

    # Success - return file content
    return response_type(
        content=content,
        status_code=HTTP_OK,
        file_path=file_path_str,
    )


def _patched_httpx_request(method: str, url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.request that handles file:// URLs and local file paths.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: URL to request (file://, http://, https://, etc.) or absolute file path
        **kwargs: Additional arguments for httpx.request

    Returns:
        httpx.Response or FileHttpxResponse
    """
    # Convert httpx.URL to string for checking
    url_str = str(url)

    # Fast path: Skip filesystem checks for HTTP/HTTPS/FTP URLs (99%+ of requests)
    if _is_http_url(url_str):
        return _original_httpx_request(method, url, **kwargs)

    # Handle existing file:// URLs
    if url_str.startswith("file://"):
        return _handle_file_url(url_str, response_type=FileHttpxResponse)  # type: ignore[return-value]

    # Detect and convert local file paths
    if _is_local_file_path(url_str):
        file_url = str(Path(url_str).as_uri())
        return _handle_file_url(file_url, response_type=FileHttpxResponse)  # type: ignore[return-value]

    # Delegate all other URLs to original httpx.request
    return _original_httpx_request(method, url, **kwargs)


def _patched_httpx_get(url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.get that handles file:// URLs."""
    return _patched_httpx_request("GET", url, **kwargs)


def _patched_httpx_post(url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.post that handles file:// URLs."""
    return _patched_httpx_request("POST", url, **kwargs)


def _patched_httpx_put(url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.put that handles file:// URLs."""
    return _patched_httpx_request("PUT", url, **kwargs)


def _patched_httpx_delete(url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.delete that handles file:// URLs."""
    return _patched_httpx_request("DELETE", url, **kwargs)


def _patched_httpx_patch(url: str | httpx.URL, **kwargs: Any) -> httpx.Response | FileHttpxResponse:
    """Patched httpx.patch that handles file:// URLs."""
    return _patched_httpx_request("PATCH", url, **kwargs)


def _patched_requests_get(url: str, **kwargs: Any) -> requests.Response | FileRequestsResponse:
    """Patched requests.get that handles file:// URLs and local file paths.

    Args:
        url: URL to request (file://, http://, https://, etc.) or absolute file path
        **kwargs: Additional arguments for requests.get

    Returns:
        requests.Response or FileRequestsResponse
    """
    # Fast path: Skip filesystem checks for HTTP/HTTPS/FTP URLs (99%+ of requests)
    if _is_http_url(url):
        return _original_requests_get(url, **kwargs)

    # Handle existing file:// URLs
    if url.startswith("file://"):
        return _handle_file_url(url, response_type=FileRequestsResponse)  # type: ignore[return-value]

    # Detect and convert local file paths
    if _is_local_file_path(url):
        file_url = str(Path(url).as_uri())
        return _handle_file_url(file_url, response_type=FileRequestsResponse)  # type: ignore[return-value]

    # Delegate all other URLs to original requests.get
    return _original_requests_get(url, **kwargs)


def install_file_url_support() -> None:
    """Install file:// URL support by patching httpx and requests at module level.

    This should be called once at app initialization. Subsequent calls are no-ops.
    """
    global _patches_installed  # noqa: PLW0603
    global _original_httpx_request  # noqa: PLW0603
    global _original_httpx_get  # noqa: PLW0603
    global _original_httpx_post  # noqa: PLW0603
    global _original_httpx_put  # noqa: PLW0603
    global _original_httpx_delete  # noqa: PLW0603
    global _original_httpx_patch  # noqa: PLW0603
    global _original_requests_get  # noqa: PLW0603

    # Prevent double-installation
    if _patches_installed:
        logger.debug("file:// URL support already installed, skipping")
        return

    logger.debug("Installing file:// URL support for httpx and requests")

    # Save original functions
    _original_httpx_request = httpx.request
    _original_httpx_get = httpx.get
    _original_httpx_post = httpx.post
    _original_httpx_put = httpx.put
    _original_httpx_delete = httpx.delete
    _original_httpx_patch = httpx.patch
    _original_requests_get = requests.get

    # Install patches
    httpx.request = _patched_httpx_request
    httpx.get = _patched_httpx_get
    httpx.post = _patched_httpx_post
    httpx.put = _patched_httpx_put
    httpx.delete = _patched_httpx_delete
    httpx.patch = _patched_httpx_patch
    requests.get = _patched_requests_get

    _patches_installed = True
    logger.debug("file:// URL support installed successfully")
