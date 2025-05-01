import base64

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader


def dict_to_image_artifact(image_dict: dict, image_format: str | None = None) -> ImageArtifact | ImageUrlArtifact:
    """Convert a dictionary representation of an image to an ImageArtifact."""
    # Get the base64 encoded string
    value = image_dict["value"]
    if image_dict["type"] == "ImageUrlArtifact":
        return ImageUrlArtifact(value)

    # If the base64 string has a prefix like "data:image/png;base64,", remove it
    if "base64," in value:
        value = value.split("base64,")[1]

    # Decode the base64 string to bytes
    image_bytes = base64.b64decode(value)

    # Determine the format from the MIME type if not specified
    if not image_format and "type" in image_dict:
        # Extract format from MIME type (e.g., 'image/png' -> 'png')
        mime_format = image_dict["type"].split("/")[1] if "/" in image_dict["type"] else None
        image_format = mime_format
    loader = ImageLoader(format=image_format)
    image_artifact = loader.try_parse(image_bytes)

    return image_artifact
