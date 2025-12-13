import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

logger = logging.getLogger("griptape_nodes")

# Default timeout for HTTP requests
DEFAULT_HTTP_TIMEOUT = 30.0


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


def uri_to_path(uri: str) -> Path:
    """Convert a file URI to a file system path."""
    parsed = urlparse(uri)
    return Path(url2pathname(parsed.path))
