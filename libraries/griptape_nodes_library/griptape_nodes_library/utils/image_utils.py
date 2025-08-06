import base64
import io
import logging
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.error import URLError

import httpx
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL import Image, ImageDraw
from requests.exceptions import RequestException

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)

# Constants for placeholder images
DEFAULT_PLACEHOLDER_WIDTH = 400
DEFAULT_PLACEHOLDER_HEIGHT = 300
DEFAULT_TIMEOUT = 30


@dataclass
class ResizedImageResult:
    """Result of resizing an image for a cell."""

    image: Image.Image | None
    x_offset: int
    y_offset: int


def parse_hex_color(color: str) -> tuple[int, int, int]:
    """Parse hex color string to RGB tuple."""
    color = color.removeprefix("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def create_background_image(width: int, height: int, background_color: str, *, transparent_bg: bool) -> Image.Image:
    """Create background image with specified color and transparency."""
    if transparent_bg:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rgb_color = parse_hex_color(background_color)
    return Image.new("RGB", (width, height), rgb_color)


def resize_image_for_cell(
    img: Image.Image, cell_width: int, cell_height: int, *, crop_to_fit: bool
) -> ResizedImageResult:
    """Resize image to fit cell and return image with positioning offsets."""
    if crop_to_fit:
        # Crop to square - resize to fit the larger dimension, then crop to square
        img_resized = img.copy()
        # Validate image dimensions to prevent division by zero
        if img.width <= 0 or img.height <= 0:
            return ResizedImageResult(None, 0, 0)  # Skip invalid images
        # Calculate scale to fit the larger dimension
        scale_x = cell_width / img.width
        scale_y = cell_height / img.height
        scale = max(scale_x, scale_y)  # Use larger scale to ensure coverage

        # Resize to cover the cell
        new_width = int(img.width * scale)
        new_height = int(img.height * scale)
        img_resized = img_resized.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Crop to square from center
        left = (new_width - cell_width) // 2
        top = (new_height - cell_height) // 2
        right = left + cell_width
        bottom = top + cell_height
        img_resized = img_resized.crop((left, top, right, bottom))

        # Position at exact cell coordinates
        x_offset = 0
        y_offset = 0
    else:
        # Scale to fit - maintain aspect ratio within cell bounds
        img_resized = img.copy()
        img_resized.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)

        # Center the image within the cell
        x_offset = (cell_width - img_resized.width) // 2
        y_offset = (cell_height - img_resized.height) // 2

    return ResizedImageResult(img_resized, x_offset, y_offset)


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
    response = httpx.get(url, timeout=DEFAULT_TIMEOUT)
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

    return ImageLoader().parse(image_bytes)


def _extract_from_rgb(image: Image.Image, channel: str) -> Image.Image:
    """Extract channel from RGB image."""
    red, green, blue = image.split()
    if channel == "red":
        return red
    if channel == "green":
        return green
    if channel == "blue":
        return blue
    # alpha not available in RGB, use red as fallback
    return red


def _extract_from_rgba(image: Image.Image, channel: str) -> Image.Image:
    """Extract channel from RGBA image."""
    red, green, blue, alpha = image.split()
    if channel == "red":
        return red
    if channel == "green":
        return green
    if channel == "blue":
        return blue
    if channel == "alpha":
        return alpha
    # Fallback to red channel
    return red


def _extract_from_la(image: Image.Image, channel: str) -> Image.Image:
    """Extract channel from LA image."""
    if channel == "alpha":
        _, alpha = image.split()
        return alpha
    gray, _ = image.split()
    return gray


def extract_channel_from_image(image: Image.Image, channel: str, context_name: str = "image") -> Image.Image:
    """Extract the specified channel from an image.

    Args:
        image: PIL Image to extract channel from
        channel: Channel to extract ("red", "green", "blue", "alpha")
        context_name: Name for error messages (e.g., "mask", "image")

    Returns:
        PIL Image containing the extracted channel

    Raises:
        ValueError: If the image mode is not supported
    """
    if image.mode == "L":
        return image
    if image.mode == "LA":
        return _extract_from_la(image, channel)
    if image.mode == "RGB":
        return _extract_from_rgb(image, channel)
    if image.mode == "RGBA":
        return _extract_from_rgba(image, channel)

    msg = f"Unsupported {context_name} mode: {image.mode}"
    raise ValueError(msg)


# New functions for DisplayImageGrid


def create_placeholder_image(width: int, height: int, background_color: str, *, transparent_bg: bool) -> Image.Image:
    """Create a placeholder image with specified dimensions and background."""
    if transparent_bg:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    else:
        # Convert hex color to RGB
        background_color = background_color.removeprefix("#")
        rgb_color = tuple(int(background_color[i : i + 2], 16) for i in (0, 2, 4))
        image = Image.new("RGB", (width, height), rgb_color)

    return image


def create_default_placeholder(
    background_color: str,
    width: int = DEFAULT_PLACEHOLDER_WIDTH,
    height: int = DEFAULT_PLACEHOLDER_HEIGHT,
    *,
    transparent_bg: bool,
) -> Image.Image:
    """Create a default placeholder image with specified or standard dimensions."""
    return create_placeholder_image(width, height, background_color, transparent_bg=transparent_bg)


def image_to_bytes(image: Image.Image, output_format: str) -> bytes:
    """Convert PIL image to bytes in specified format."""
    buffer = io.BytesIO()
    image.save(buffer, format=output_format.upper())
    return buffer.getvalue()


def extract_image_url(image_item: Any) -> str:
    """Extract URL from various image input types."""
    if isinstance(image_item, ImageUrlArtifact):
        return image_item.value
    if isinstance(image_item, dict) and "value" in image_item:
        return image_item["value"]
    if isinstance(image_item, str):
        return image_item
    # Try to load from URL if it's a string
    return str(image_item)


def load_images_from_list(images: list) -> list[Image.Image]:
    """Load PIL images from a list of image items, skipping invalid ones."""
    pil_images = []
    for img_item in images:
        try:
            url = extract_image_url(img_item)
            pil_img = load_pil_from_url(url)
            # Validate image dimensions
            if pil_img.width <= 0 or pil_img.height <= 0:
                msg = f"Skipping image with invalid dimensions: {pil_img.width}x{pil_img.height}"
                logger.warning(msg)
                continue
            pil_images.append(pil_img)
        except (URLError, RequestException, ConnectionError, TimeoutError, OSError) as e:
            # Skip invalid images
            msg = f"Skipping invalid image: {e}"
            logger.warning(msg)
            continue
    return pil_images


def create_grid_layout(  # noqa: PLR0913
    images: list,
    columns: int,
    output_image_width: int,
    spacing: int,
    background_color: str,
    border_radius: int,
    *,
    crop_to_fit: bool,
    transparent_bg: bool,
) -> Image.Image:
    """Create a uniform grid layout of images."""
    if not images:
        return create_default_placeholder(
            background_color, transparent_bg=transparent_bg, width=output_image_width, height=output_image_width
        )

    # Load and process images
    pil_images = load_images_from_list(images)

    if not pil_images:
        return create_default_placeholder(background_color, transparent_bg=transparent_bg)

    # Calculate grid dimensions
    if columns <= 0:
        return create_default_placeholder(background_color, transparent_bg=transparent_bg)

    rows = (len(pil_images) + columns - 1) // columns
    cell_width = (output_image_width - spacing * (columns + 1)) // columns
    cell_height = cell_width  # Square cells for grid layout

    # Create background
    total_width = cell_width * columns + spacing * (columns + 1)
    total_height = cell_height * rows + spacing * (rows + 1)
    grid_image = create_background_image(total_width, total_height, background_color, transparent_bg=transparent_bg)

    # Place images in grid
    for idx, img in enumerate(pil_images):
        row = idx // columns
        col = idx % columns

        # Resize image to fit cell
        resized_result = resize_image_for_cell(img, cell_width, cell_height, crop_to_fit)
        if resized_result.image is None:
            continue  # Skip invalid images

        # Apply border radius if specified
        if border_radius > 0:
            resized_result.image = apply_border_radius(resized_result.image, border_radius)

        # Calculate final position
        final_x = col * cell_width + spacing + resized_result.x_offset
        final_y = row * cell_height + spacing + resized_result.y_offset
        grid_image.paste(
            resized_result.image,
            (final_x, final_y),
            resized_result.image if resized_result.image.mode == "RGBA" else None,
        )

    return grid_image


def create_masonry_layout(  # noqa: C901, PLR0913
    images: list,
    columns: int,
    output_image_width: int,
    spacing: int,
    background_color: str,
    border_radius: int,
    *,
    transparent_bg: bool,
) -> Image.Image:
    """Create a masonry layout with variable height columns."""
    if not images:
        return create_default_placeholder(background_color, transparent_bg=transparent_bg)

    # Load and process images
    pil_images = load_images_from_list(images)

    if not pil_images:
        return create_default_placeholder(background_color, transparent_bg=transparent_bg)

    # Calculate column width
    if columns <= 0:
        return create_default_placeholder(background_color, transparent_bg=transparent_bg)

    column_width = (output_image_width - spacing * (columns + 1)) // columns

    # Distribute images across columns
    columns_content = [[] for _ in range(columns)]
    column_heights = [0] * columns

    for _idx, img in enumerate(pil_images):
        # Find shortest column
        shortest_col = column_heights.index(min(column_heights))
        columns_content[shortest_col].append(img)

        # Calculate height for this image
        if img.width <= 0 or img.height <= 0:
            continue  # Skip invalid images
        aspect_ratio = img.width / img.height
        img_height = int(column_width / aspect_ratio)
        column_heights[shortest_col] += img_height + spacing

    # Create background
    total_height = max(column_heights) + spacing
    grid_image = create_background_image(
        output_image_width, total_height, background_color, transparent_bg=transparent_bg
    )

    # Place images in columns
    for col_idx, column_images in enumerate(columns_content):
        x_offset = col_idx * column_width + spacing * (col_idx + 1)
        y_offset = spacing

        for img in column_images:
            # Resize image to fit column width
            img_resized = img.copy()
            if img.width <= 0 or img.height <= 0:
                continue  # Skip invalid images
            aspect_ratio = img.width / img.height
            if aspect_ratio <= 0:
                continue  # Skip images with invalid aspect ratio
            img_height = int(column_width / aspect_ratio)
            img_resized = img_resized.resize((column_width, img_height), Image.Resampling.LANCZOS)

            # Apply border radius if specified
            if border_radius > 0:
                img_resized = apply_border_radius(img_resized, border_radius)

            grid_image.paste(img_resized, (x_offset, y_offset), img_resized if img_resized.mode == "RGBA" else None)
            y_offset += img_height + spacing

    return grid_image


def apply_border_radius(image: Image.Image, radius: int) -> Image.Image:
    """Apply border radius to an image."""
    if radius <= 0:
        return image

    # Create a mask with rounded corners
    mask = Image.new("L", image.size, 0)

    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), image.size], radius=radius, fill=255)

    # Apply mask
    if image.mode == "RGBA":
        result = image.copy()
        result.putalpha(Image.composite(image.getchannel("A"), Image.new("L", image.size, 0), mask))
    else:
        result = image.convert("RGBA")
        result.putalpha(mask)

    return result


def cleanup_temp_files() -> None:
    """Clean up temporary files (placeholder for compatibility)."""
    # This is a placeholder function for compatibility
    # In this implementation, we don't need to clean up temp files
    # as we're using the static file manager
