import logging
import mimetypes
from typing import Literal
from urllib.parse import urlparse

import httpx
from upath import UPath as Path

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
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URL (http://, https://, or file://).

    UPath natively supports all protocols through fsspec.

    Args:
        url: URL to load from
        timeout: Timeout in seconds (note: timeout handling depends on fsspec backend)
        validate_scheme: Whether to validate URL scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URL scheme is invalid
        FileNotFoundError: If file not found
        Exception: Other fsspec-related errors
    """
    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    # UPath handles all URL schemes through fsspec
    path = Path(url)
    return path.read_bytes()


async def aload_content_from_url(
    url: str,
    *,
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URL asynchronously (http://, https://, or file://).

    UPath natively supports all protocols through fsspec.

    Args:
        url: URL to load from
        timeout: Timeout in seconds (note: timeout handling depends on fsspec backend)
        validate_scheme: Whether to validate URL scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URL scheme is invalid
        FileNotFoundError: If file not found
        Exception: Other fsspec-related errors
    """
    import asyncio

    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    # UPath handles all URL schemes through fsspec
    # Wrap synchronous read_bytes in thread to make it async
    path = Path(url)
    return await asyncio.to_thread(path.read_bytes)


async def stream_download_to_file(
    url: str,
    destination: Path,
    *,
    validate_scheme: bool = True,
) -> Path:
    """Download content from URL to a file.

    UPath natively supports all protocols through fsspec.

    Args:
        url: URL to download from
        destination: Destination file path
        timeout: Timeout in seconds (note: timeout handling depends on fsspec backend)
        validate_scheme: Whether to validate URL scheme

    Returns:
        Path to the downloaded file

    Raises:
        ValueError: If URL is invalid
        FileNotFoundError: If source file not found
        Exception: Other fsspec-related errors
    """
    import asyncio

    if validate_scheme and not validate_url(url):
        msg = f"Invalid URL: {url}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    # UPath handles all URL schemes through fsspec
    source_path = Path(url)

    # Load and write using async wrapper
    content = await asyncio.to_thread(source_path.read_bytes)
    await asyncio.to_thread(destination.write_bytes, content)

    return destination


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

    # For file:// URLs, use extension - UPath natively supports file:// URIs
    if parsed.scheme == "file":
        file_path = Path(url)
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
