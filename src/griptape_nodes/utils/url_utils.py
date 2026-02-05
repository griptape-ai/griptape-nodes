import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

logger = logging.getLogger("griptape_nodes")

# Default timeout for HTTP requests
DEFAULT_HTTP_TIMEOUT = 30.0


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


def uri_to_path(uri: str) -> Path:
    """Convert a file URI to a file system path."""
    # TODO: replace with Path.from_uri() when we upgrade to python >=3.13
    # https://docs.python.org/3/library/pathlib.html#pathlib.Path.from_uri
    parsed = urlparse(uri)
    return Path(url2pathname(parsed.path))


def is_http_url(location: str) -> bool:
    """Check if a location is an HTTP/HTTPS URL.

    Args:
        location: Location string to check

    Returns:
        True if location is an HTTP/HTTPS URL
    """
    return location.startswith(("http://", "https://"))


def is_file_location(location: str) -> bool:
    """Check if a location is a file path (file:// URL or local path).

    Args:
        location: Location string to check

    Returns:
        True if location is a file:// URL or local path
    """
    if location.startswith("file://"):
        return True

    # Check if it's a local path by attempting to create a Path object
    # Exclude other URI schemes (data:, ftp:, mailto:, etc.)
    if "://" in location:
        return False

    if ":" in location and location[1:3] != ":\\" and location[0] != "/":
        return False

    try:
        Path(location)
    except (ValueError, OSError):
        return False
    else:
        return True


def location_to_path(location: str) -> str:
    """Convert a file location (file:// URL or local path) to a path string.

    Args:
        location: Location string (file:// URL or local path)

    Returns:
        Path string
    """
    if location.startswith("file://"):
        parsed = urlparse(location)
        return url2pathname(parsed.path)

    return location


def is_url_or_path(value: str) -> bool:
    """Check if a value is a URL or file path.

    This utility determines if a string represents a fetchable resource
    (URL or file path) without validating reachability or existence.

    Returns True for:
        - HTTP/HTTPS URLs: http://example.com/file.txt
        - file:// URLs: file:///path/to/file
        - File system paths (absolute or relative)

    Returns False for:
        - data: URIs (inline data, not fetchable)
        - Other URI schemes (ftp://, mailto:, etc.)
        - Empty strings or whitespace
        - Plain text without path indicators

    Note:
        This function does NOT check if URLs are reachable or if
        file paths exist. It only validates the format.

    Args:
        value: String to check

    Returns:
        True if value looks like a URL or path, False otherwise

    Examples:
        >>> is_url_or_path("https://example.com/image.png")
        True
        >>> is_url_or_path("file:///path/to/file.txt")
        True
        >>> is_url_or_path("/absolute/path/file.txt")
        True
        >>> is_url_or_path("./relative/path.txt")
        True
        >>> is_url_or_path("data:image/png;base64,...")
        False
        >>> is_url_or_path("ftp://ftp.example.com")
        False
        >>> is_url_or_path("")
        False
    """
    # Guard: empty or whitespace-only strings
    if not value or not value.strip():
        return False

    # Fast path: Check for known URL schemes
    if value.startswith(("http://", "https://", "file://")):
        return True

    # Exclude other URI schemes (data:, ftp:, mailto:, javascript:, etc.)
    # Check for :// (full URI schemes) and single : schemes
    if "://" in value or (
        ":" in value
        and value[1:3] != ":\\"  # Allow Windows drive letters (C:\)
        and value[0] != "/"  # Allow Unix paths with : in filename
    ):
        return False

    # Check if it's a valid file path by attempting to create a Path object
    # Path() handles cross-platform paths (Unix, Windows, UNC)
    try:
        Path(value)
    except (ValueError, OSError):
        # Invalid path (e.g., contains illegal characters on Windows)
        return False
    else:
        return True
