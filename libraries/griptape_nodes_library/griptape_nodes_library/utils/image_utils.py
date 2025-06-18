import base64
import io
import logging
import uuid
from io import BytesIO
from typing import Any
from urllib.error import URLError

import httpx
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL import ExifTags, Image
from requests.exceptions import RequestException

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.utils.artifact_utils import add_common_metadata, set_artifact_properties

logger = logging.getLogger(__name__)


def dict_to_image_url_artifact(image_dict: dict, image_format: str | None = None) -> ImageUrlArtifact:
    """Convert a dictionary representation of an image to an ImageUrlArtifact."""
    logger.info("Starting dict_to_image_url_artifact")
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

    # Create temporary ImageArtifact to add metadata
    temp_artifact = ImageLoader().parse(image_bytes)
    add_image_metadata(temp_artifact, image_bytes)

    # Debug: Check metadata after adding
    logger.debug("Metadata after adding: %s", temp_artifact.meta)

    # Save to static file and create URL artifact with metadata
    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.{image_format}")
    artifact = ImageUrlArtifact(url, meta=temp_artifact.meta)

    # Debug: Check metadata after creating URL artifact
    logger.debug("Metadata in URL artifact: %s", artifact.meta)

    return artifact


def save_pil_image_to_static_file(image: Image.Image, image_format: str = "PNG") -> ImageUrlArtifact:
    """Save a PIL image to the static file system and return an ImageUrlArtifact."""
    logger.info("Starting save_pil_image_to_static_file")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    image_bytes = buffer.getvalue()

    # Create temporary ImageArtifact to add metadata
    temp_artifact = ImageLoader().parse(image_bytes)
    add_image_metadata(temp_artifact, image_bytes)

    # Debug: Check metadata after adding
    logger.debug("Metadata after adding: %s", temp_artifact.meta)

    # Save to static file and create URL artifact with metadata
    filename = f"{uuid.uuid4()}.{image_format.lower()}"
    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, filename)
    artifact = ImageUrlArtifact(url, meta=temp_artifact.meta)

    # Debug: Check metadata after creating URL artifact
    logger.debug("Metadata in URL artifact: %s", artifact.meta)

    return artifact


def load_pil_from_url(url: str) -> Image.Image:
    """Load image from URL using httpx."""
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))


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
        image_bytes = image_url_artifact.to_bytes()
    except (URLError, RequestException, ConnectionError, TimeoutError) as err:
        details = (
            f"Failed to download image at '{image_url_artifact.value}'.\n"
            f"If this workflow was shared from another engine installation, "
            f"that image file will need to be regenerated.\n"
            f"Error: {err}"
        )
        raise ValueError(details) from err

    artifact = ImageLoader().parse(image_bytes)
    add_image_metadata(artifact, image_bytes)
    return artifact


def add_image_metadata(artifact: ImageArtifact, image_bytes: bytes) -> None:
    """Add image-specific metadata to an ImageArtifact.

    Args:
        artifact: The ImageArtifact to add metadata to
        image_bytes: The image data in bytes
    """
    # Add common metadata first
    add_common_metadata(artifact, image_bytes)

    # Get image properties using PIL
    with Image.open(BytesIO(image_bytes)) as img:
        # Basic properties
        properties = {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
            "dpi": img.info.get("dpi", (72, 72)),
            "color_space": img.mode,
            "has_alpha": img.mode in ("RGBA", "LA"),
            "is_animated": getattr(img, "is_animated", False),
            "frame_count": getattr(img, "n_frames", 1),
            # M&E specific properties
            "aspect_ratio": round(img.width / img.height, 3),
            "megapixels": round((img.width * img.height) / 1_000_000, 2),
            "bit_depth": img.bits if hasattr(img, "bits") else None,  # type: ignore[attr-defined]
            "compression": img.info.get("compression"),
            "icc_profile": bool(img.info.get("icc_profile")),
        }

        # Extract EXIF data if available
        exif_data = {}
        if hasattr(img, "_getexif") and img._getexif():  # type: ignore[attr-defined]
            for tag_id, value in img._getexif().items():  # type: ignore[attr-defined]
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if isinstance(value, (int, float, str, bool)):
                    exif_data[tag] = value
                elif isinstance(value, bytes):
                    try:
                        exif_data[tag] = value.decode("utf-8")
                    except UnicodeDecodeError:
                        continue

        if exif_data:
            properties["exif"] = exif_data

        # Add color profile information
        if hasattr(img, "getbands"):
            properties["channels"] = len(img.getbands())
            properties["channel_names"] = img.getbands()

    set_artifact_properties(artifact, properties)


def get_image_dimensions(artifact: ImageArtifact) -> tuple[int, int]:
    """Get the width and height of an image.

    Args:
        artifact: The ImageArtifact to get dimensions from

    Returns:
        Tuple of (width, height)
    """
    props = artifact.meta.get("properties", {})
    return props.get("width", 0), props.get("height", 0)


def get_image_format(artifact: ImageArtifact) -> str | None:
    """Get the format of an image (e.g., 'JPEG', 'PNG').

    Args:
        artifact: The ImageArtifact to get format from

    Returns:
        The image format or None if not available
    """
    return artifact.meta.get("properties", {}).get("format")


def is_animated_image(artifact: ImageArtifact) -> bool:
    """Check if the image is animated (e.g., GIF).

    Args:
        artifact: The ImageArtifact to check

    Returns:
        True if the image is animated
    """
    return artifact.meta.get("properties", {}).get("is_animated", False)


def get_image_dpi(artifact: ImageArtifact) -> tuple[float, float]:
    """Get the DPI (dots per inch) of an image.

    Args:
        artifact: The ImageArtifact to get DPI from

    Returns:
        Tuple of (x_dpi, y_dpi)
    """
    return artifact.meta.get("properties", {}).get("dpi", (72.0, 72.0))


def get_aspect_ratio(artifact: ImageArtifact) -> float:
    """Get the aspect ratio of an image.

    Args:
        artifact: The ImageArtifact to get aspect ratio from

    Returns:
        The aspect ratio (width/height)
    """
    return artifact.meta.get("properties", {}).get("aspect_ratio", 0.0)


def get_megapixels(artifact: ImageArtifact) -> float:
    """Get the resolution in megapixels.

    Args:
        artifact: The ImageArtifact to get megapixels from

    Returns:
        Resolution in megapixels
    """
    return artifact.meta.get("properties", {}).get("megapixels", 0.0)


def get_color_profile_info(artifact: ImageArtifact) -> dict[str, Any]:
    """Get color profile information.

    Args:
        artifact: The ImageArtifact to get color info from

    Returns:
        Dictionary containing color profile information
    """
    props = artifact.meta.get("properties", {})
    return {
        "color_space": props.get("color_space"),
        "channels": props.get("channels"),
        "channel_names": props.get("channel_names"),
        "bit_depth": props.get("bit_depth"),
        "has_icc_profile": props.get("icc_profile", False),
    }


def get_exif_data(artifact: ImageArtifact) -> dict[str, Any]:
    """Get EXIF metadata if available.

    Args:
        artifact: The ImageArtifact to get EXIF data from

    Returns:
        Dictionary of EXIF data
    """
    return artifact.meta.get("properties", {}).get("exif", {})
