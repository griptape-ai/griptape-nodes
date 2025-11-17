import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

logger = logging.getLogger("griptape_nodes")

# Default timeout for HTTP requests
DEFAULT_HTTP_TIMEOUT = 30.0


def is_url(value: str) -> bool:
    """Check if a string looks like a URL (has scheme://).

    Args:
        value: String to check

    Returns:
        True if value contains a URL scheme (e.g., http://, file://, s3://)
    """
    # Generic check: does it have a scheme?
    # Let UPath/fsspec handle the actual protocol
    parsed = urlparse(value)
    return bool(parsed.scheme)


def validate_url(url: str, *, allowed_schemes: tuple[str, ...] | None = None) -> bool:
    """Validate that a URL has basic correct structure.

    Generic validation - just checks URL has a scheme and isn't obviously malformed.
    UPath/fsspec will handle protocol-specific validation.

    Args:
        url: URL to validate
        allowed_schemes: Optional tuple of allowed scheme names. If None (default),
                        any scheme is allowed. Use for restricting to specific protocols.

    Returns:
        True if URL has valid structure, False otherwise
    """
    parsed = urlparse(url)

    # Must have a scheme
    if not parsed.scheme:
        return False

    # If allowed_schemes specified, check scheme is in the list
    if allowed_schemes is not None and parsed.scheme not in allowed_schemes:
        return False

    # Basic validation: must have either netloc or path
    # This catches truly malformed URLs like "http://" with nothing after
    return bool(parsed.netloc or parsed.path)


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
