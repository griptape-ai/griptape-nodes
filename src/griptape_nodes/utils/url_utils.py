import logging
import mimetypes
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx

logger = logging.getLogger("griptape_nodes")

# Default timeout for HTTP requests
DEFAULT_HTTP_TIMEOUT = 30.0

# Supported URL schemes
SUPPORTED_SCHEMES = ("http", "https", "file")


def is_url(value: str) -> bool:
    """Check if a string is a supported URL.

    Args:
        value: String to check

    Returns:
        True if value starts with http://, https://, or file://
    """
    return value.startswith(("http://", "https://", "file://"))


def get_url_scheme(url: str) -> str | None:
    """Get the scheme from a URL.

    Args:
        url: URL string to parse

    Returns:
        The scheme (e.g., "http", "https", "file") or None if invalid
    """
    parsed = urlparse(url)
    return parsed.scheme if parsed.scheme else None


def validate_url(url: str, *, allowed_schemes: tuple[str, ...] = SUPPORTED_SCHEMES) -> bool:
    """Validate that a URL has a supported scheme and proper format.

    Args:
        url: URL to validate
        allowed_schemes: Tuple of allowed scheme names (default: http, https, file)

    Returns:
        True if URL is valid, False otherwise
    """
    parsed = urlparse(url)

    # Check if scheme is allowed
    if parsed.scheme not in allowed_schemes:
        return False

    # For http/https, require netloc (domain)
    if parsed.scheme in ("http", "https"):
        return bool(parsed.netloc)

    # For file://, require absolute path (starts with /)
    if parsed.scheme == "file":
        # file:// URLs should have path starting with / for absolute paths
        # file:///absolute/path is correct format
        return parsed.path.startswith("/")

    return False


def get_content_type_from_extension(file_path: str | Path) -> str | None:
    """Get content type from file extension.

    Args:
        file_path: Path or URL with file extension

    Returns:
        MIME type string or None if unknown
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Use mimetypes to guess from extension
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type


def strip_file_scheme(url: str) -> str:
    """Strip file:// scheme from URL, pass through other URLs/paths unchanged.

    Some libraries (like diffusers.utils.load_video) support HTTP/HTTPS URLs
    and local file paths, but NOT file:// URLs. This helper converts file://
    URLs to paths so they can be used with such libraries.

    Args:
        url: A URL (http://, https://, file://) or file path

    Returns:
        For file:// URLs: the extracted file path
        For other inputs: the original string unchanged
    """
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return url2pathname(parsed.path)
    return url


def validate_content_type_for_category(
    content_type: str | None,
    expected_category: Literal["image", "video", "audio"],
) -> bool:
    """Validate that content type matches expected media category.

    Args:
        content_type: MIME type string (e.g., "image/jpeg")
        expected_category: Expected media category

    Returns:
        True if content type matches category, False otherwise
    """
    if content_type is None:
        return False

    return content_type.startswith(f"{expected_category}/")


def load_content_from_url(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URL (http://, https://, or file://).

    Args:
        url: URL to load from
        timeout: Timeout in seconds for HTTP requests (ignored for file://)
        validate_scheme: Whether to validate URL scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URL scheme is invalid or file:// path is not absolute
        FileNotFoundError: If file:// URL points to non-existent file
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(url)

    # Handle file:// URLs
    if parsed.scheme == "file":
        # Parse file path from URL
        # file:///path/to/file -> /path/to/file
        file_path = Path(url2pathname(parsed.path))

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {file_path}"
            raise ValueError(msg)

        return file_path.read_bytes()

    # Handle http:// and https:// URLs
    if parsed.scheme in ("http", "https"):
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URL scheme: {parsed.scheme}"
    raise ValueError(msg)


async def aload_content_from_url(
    url: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,  # noqa: ASYNC109
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URL asynchronously (http://, https://, or file://).

    Args:
        url: URL to load from
        timeout: Timeout in seconds for HTTP requests (ignored for file://)
        validate_scheme: Whether to validate URL scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URL scheme is invalid or file:// path is not absolute
        FileNotFoundError: If file:// URL points to non-existent file
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(url)

    # Handle file:// URLs - file operations are synchronous
    if parsed.scheme == "file":
        file_path = Path(url2pathname(parsed.path))

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {file_path}"
            raise ValueError(msg)

        return file_path.read_bytes()

    # Handle http:// and https:// URLs asynchronously
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URL scheme: {parsed.scheme}"
    raise ValueError(msg)


async def stream_download_to_file(
    url: str,
    destination: Path,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,  # noqa: ASYNC109
    validate_scheme: bool = True,
) -> Path:
    """Stream download content from URL to a file.

    For file:// URLs, simply copies the file.
    For http:// and https:// URLs, streams the download.

    Args:
        url: URL to download from
        destination: Destination file path
        timeout: Timeout in seconds for HTTP requests
        validate_scheme: Whether to validate URL scheme

    Returns:
        Path to the downloaded file

    Raises:
        ValueError: If URL is invalid
        FileNotFoundError: If source file not found (for file:// URLs)
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(url)

    # Handle file:// URLs - just copy the file
    if parsed.scheme == "file":
        source_path = Path(url2pathname(parsed.path))

        if not source_path.exists():
            msg = f"File not found: {source_path}"
            raise FileNotFoundError(msg)

        if not source_path.is_file():
            msg = f"Path is not a file: {source_path}"
            raise ValueError(msg)

        # Copy file content
        destination.write_bytes(source_path.read_bytes())
        return destination

    # Handle http:// and https:// URLs - stream download
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream("GET", url) as response:
            response.raise_for_status()

            with destination.open("wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

        return destination

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URL scheme: {parsed.scheme}"
    raise ValueError(msg)


def get_content_type_from_url(url: str) -> str | None:
    """Get content type for a URL.

    For http/https URLs, makes a HEAD request to get Content-Type header.
    For file:// URLs, guesses from file extension.

    Args:
        url: URL to check

    Returns:
        Content type string or None if unable to determine
    """
    parsed = urlparse(url)

    # For file:// URLs, use extension
    if parsed.scheme == "file":
        file_path = Path(url2pathname(parsed.path))
        return get_content_type_from_extension(file_path)

    # For http/https URLs, make HEAD request
    if parsed.scheme in ("http", "https"):
        try:
            response = httpx.head(url, timeout=DEFAULT_HTTP_TIMEOUT)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            # Split to remove charset and other parameters
            return content_type.split(";")[0].strip()
        except Exception as e:
            logger.warning("Failed to get content type from %s: %s", url, e)
            return None

    return None
