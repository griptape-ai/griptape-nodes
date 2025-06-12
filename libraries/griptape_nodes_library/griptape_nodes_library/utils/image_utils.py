import base64
import io
import uuid
from io import BytesIO
from typing import Any

import httpx
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


def dict_to_image_url_artifact(image_dict: dict, image_format: str | None = None) -> ImageUrlArtifact:
    """Convert a dictionary representation of an image to an ImageUrlArtifact."""
    value = image_dict["value"]
    if image_dict["type"] == "ImageUrlArtifact":
        return ImageUrlArtifact(value)

    # Strip base64 prefix if needed
    if "base64," in value:
        value = value.split("base64,")[1]

    image_bytes = base64.b64decode(value)

    # Infer format from MIME type if not specified
    if image_format is None:
        if "type" in image_dict:
            mime_format = image_dict["type"].split("/")[1] if "/" in image_dict["type"] else None
            image_format = mime_format
        else:
            image_format = "png"

    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.{image_format}")
    return ImageUrlArtifact(url)


def save_pil_image_to_static_file(image: Image.Image, image_format: str = "PNG") -> ImageUrlArtifact:
    """Save a PIL image to the static file system and return an ImageUrlArtifact."""
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    image_bytes = buffer.getvalue()

    filename = f"{uuid.uuid4()}.{image_format.lower()}"
    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, filename)

    return ImageUrlArtifact(url)


def load_pil_from_url(url: str) -> Image.Image:
    """Load image from URL using httpx."""
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))


def normalize_image_input(value: Any) -> ImageUrlArtifact:
    """Normalize various image input types to ImageUrlArtifact."""
    if isinstance(value, dict):
        return dict_to_image_url_artifact(value)
    return value


def create_alpha_mask(image: Image.Image) -> Image.Image:
    """Create a mask from an image's alpha channel.

    Args:
        image: PIL Image to create mask from

    Returns:
        PIL Image with black background and white mask
    """
    # Convert to RGBA if needed
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Extract alpha channel
    mask = image.getchannel("A")

    # Convert to RGB (black background with white mask)
    mask_rgb = Image.new("RGB", mask.size, (0, 0, 0))
    mask_rgb.paste((255, 255, 255), mask=mask)

    return mask_rgb
