from urllib.error import URLError

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader
from requests.exceptions import RequestException

from griptape_nodes.utils.url_utils import load_content_from_uri


def load_image_from_url_artifact(image_url_artifact: ImageUrlArtifact) -> ImageArtifact:
    """Load an ImageArtifact from an ImageUrlArtifact with proper error handling.

    Args:
        image_url_artifact: The ImageUrlArtifact to load

    Returns:
        ImageArtifact: The loaded image artifact

    Raises:
        ValueError: If image download fails with descriptive error message
    """
    try:
        # Use load_content_from_uri which handles file://, http://, and https:// URIs
        image_bytes = load_content_from_uri(image_url_artifact.value)
    except (URLError, RequestException, ConnectionError, TimeoutError, ValueError, FileNotFoundError) as err:
        details = (
            f"Failed to download image at '{image_url_artifact.value}'.\n"
            f"If this workflow was shared from another engine installation, "
            f"that image file will need to be regenerated.\n"
            f"Error: {err}"
        )
        raise ValueError(details) from err

    return ImageLoader().parse(image_bytes)
