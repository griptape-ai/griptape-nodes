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
