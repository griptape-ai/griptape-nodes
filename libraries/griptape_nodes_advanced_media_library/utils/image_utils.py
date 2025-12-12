from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


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
        image_bytes = GriptapeNodes.FileManager().read_file(image_url_artifact.value)
    except ValueError as e:
        details = (
            f"Failed to download image at '{image_url_artifact.value}'.\n"
            f"If this workflow was shared from another engine installation, "
            f"that image file will need to be regenerated.\n"
            f"Error: {e}"
        )
        raise ValueError(details) from e

    return ImageLoader().parse(image_bytes)
