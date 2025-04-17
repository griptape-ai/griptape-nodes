import base64

from griptape.artifacts import ImageArtifact
from griptape.loaders import ImageLoader


def dict_to_image_artifact(image_dict, image_format=None) -> ImageArtifact:
    # Get the base64 encoded string
    base64_data = image_dict["value"]

    # If the base64 string has a prefix like "data:image/png;base64,", remove it
    if "base64," in base64_data:
        base64_data = base64_data.split("base64,")[1]

    # Decode the base64 string to bytes
    image_bytes = base64.b64decode(base64_data)

    # Determine the format from the MIME type if not specified
    if not image_format and "type" in image_dict:
        # Extract format from MIME type (e.g., 'image/png' -> 'png')
        mime_format = image_dict["type"].split("/")[1] if "/" in image_dict["type"] else None
        image_format = mime_format

    # Method 1: Use ImageLoader to parse and get all metadata
    loader = ImageLoader(format=image_format)
    image_artifact = loader.try_parse(image_bytes)

    return image_artifact
