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

# Supported URI schemes
SUPPORTED_SCHEMES = ("http", "https", "file")


def is_url(value: str) -> bool:
    """Check if a string is a supported URL/URI.

    Args:
        value: String to check

    Returns:
        True if value starts with http://, https://, or file://
    """
    return value.startswith(("http://", "https://", "file://"))


def get_uri_scheme(uri: str) -> str | None:
    """Get the scheme from a URI.

    Args:
        uri: URI string to parse

    Returns:
        The scheme (e.g., "http", "https", "file") or None if invalid
    """
    parsed = urlparse(uri)
    return parsed.scheme if parsed.scheme else None


def validate_uri(uri: str, *, allowed_schemes: tuple[str, ...] = SUPPORTED_SCHEMES) -> bool:
    """Validate that a URI has a supported scheme and proper format.

    Args:
        uri: URI to validate
        allowed_schemes: Tuple of allowed scheme names (default: http, https, file)

    Returns:
        True if URI is valid, False otherwise
    """
    parsed = urlparse(uri)

    # Check if scheme is allowed
    if parsed.scheme not in allowed_schemes:
        return False

    # For http/https, require netloc (domain)
    if parsed.scheme in ("http", "https"):
        return bool(parsed.netloc)

    # For file://, require absolute path (starts with /)
    if parsed.scheme == "file":
        # file:// URIs should have path starting with / for absolute paths
        # file:///absolute/path is correct format
        return parsed.path.startswith("/")

    return False


def get_content_type_from_extension(file_path: str | Path) -> str | None:
    """Get content type from file extension.

    Args:
        file_path: Path or URI with file extension

    Returns:
        MIME type string or None if unknown
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Use mimetypes to guess from extension
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type


def uri_to_path_or_url(uri: str) -> str:
    """Convert file:// URI to file path, pass through other URLs/paths unchanged.

    Some libraries (like diffusers.utils.load_video) support HTTP/HTTPS URLs
    and local file paths, but NOT file:// URIs. This helper converts file://
    URIs to paths so they can be used with such libraries.

    Args:
        uri: A URL, file:// URI, or file path

    Returns:
        For file:// URIs: the extracted file path
        For other inputs: the original string unchanged
    """
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return url2pathname(parsed.path)
    return uri


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


def load_content_from_uri(
    uri: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URI (http://, https://, or file://).

    Args:
        uri: URI to load from
        timeout: Timeout in seconds for HTTP requests (ignored for file://)
        validate_scheme: Whether to validate URI scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URI scheme is invalid or file:// path is not absolute
        FileNotFoundError: If file:// URI points to non-existent file
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_uri(uri):
        msg = f"Invalid URI: {uri}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(uri)

    # Handle file:// URIs
    if parsed.scheme == "file":
        # Parse file path from URI
        # file:///path/to/file -> /path/to/file
        file_path = Path(url2pathname(parsed.path))

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {file_path}"
            raise ValueError(msg)

        return file_path.read_bytes()

    # Handle http:// and https:// URIs
    if parsed.scheme in ("http", "https"):
        response = httpx.get(uri, timeout=timeout)
        response.raise_for_status()
        return response.content

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URI scheme: {parsed.scheme}"
    raise ValueError(msg)


async def aload_content_from_uri(
    uri: str,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,  # noqa: ASYNC109
    validate_scheme: bool = True,
) -> bytes:
    """Load content from a URI asynchronously (http://, https://, or file://).

    Args:
        uri: URI to load from
        timeout: Timeout in seconds for HTTP requests (ignored for file://)
        validate_scheme: Whether to validate URI scheme before loading

    Returns:
        File content as bytes

    Raises:
        ValueError: If URI scheme is invalid or file:// path is not absolute
        FileNotFoundError: If file:// URI points to non-existent file
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_uri(uri):
        msg = f"Invalid URI: {uri}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(uri)

    # Handle file:// URIs - file operations are synchronous
    if parsed.scheme == "file":
        file_path = Path(url2pathname(parsed.path))

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {file_path}"
            raise ValueError(msg)

        return file_path.read_bytes()

    # Handle http:// and https:// URIs asynchronously
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(uri)
            response.raise_for_status()
            return response.content

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URI scheme: {parsed.scheme}"
    raise ValueError(msg)


async def stream_download_to_file(
    uri: str,
    destination: Path,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,  # noqa: ASYNC109
    validate_scheme: bool = True,
) -> Path:
    """Stream download content from URI to a file.

    For file:// URIs, simply copies the file.
    For http:// and https:// URIs, streams the download.

    Args:
        uri: URI to download from
        destination: Destination file path
        timeout: Timeout in seconds for HTTP requests
        validate_scheme: Whether to validate URI scheme

    Returns:
        Path to the downloaded file

    Raises:
        ValueError: If URI is invalid
        FileNotFoundError: If source file not found (for file:// URIs)
        httpx.HTTPError: If HTTP request fails
    """
    if validate_scheme and not validate_uri(uri):
        msg = f"Invalid URI: {uri}. Must be http://, https://, or file:// with absolute path"
        raise ValueError(msg)

    parsed = urlparse(uri)

    # Handle file:// URIs - just copy the file
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

    # Handle http:// and https:// URIs - stream download
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream("GET", uri) as response:
            response.raise_for_status()

            with destination.open("wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

        return destination

    # Should not reach here if validate_scheme is True
    msg = f"Unsupported URI scheme: {parsed.scheme}"
    raise ValueError(msg)


def get_content_type_from_uri(uri: str) -> str | None:
    """Get content type for a URI.

    For http/https URIs, makes a HEAD request to get Content-Type header.
    For file:// URIs, guesses from file extension.

    Args:
        uri: URI to check

    Returns:
        Content type string or None if unable to determine
    """
    parsed = urlparse(uri)

    # For file:// URIs, use extension
    if parsed.scheme == "file":
        file_path = Path(url2pathname(parsed.path))
        return get_content_type_from_extension(file_path)

    # For http/https URIs, make HEAD request
    if parsed.scheme in ("http", "https"):
        try:
            response = httpx.head(uri, timeout=DEFAULT_HTTP_TIMEOUT)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            # Split to remove charset and other parameters
            return content_type.split(";")[0].strip()
        except Exception as e:
            logger.warning("Failed to get content type from %s: %s", uri, e)
            return None

    return None
