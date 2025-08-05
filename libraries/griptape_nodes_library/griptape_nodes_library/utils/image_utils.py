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
from PIL import Image
from requests.exceptions import RequestException

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


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


def extract_channel_from_image(image: Image.Image, channel: str, context_name: str = "image") -> Image.Image:  # noqa: C901, PLR0911, PLR0912
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
    match image.mode:
        case "RGB":
            if channel == "red":
                r, _, _ = image.split()
                return r
            if channel == "green":
                _, g, _ = image.split()
                return g
            if channel == "blue":
                _, _, b = image.split()
                return b
            # alpha not available in RGB, use red as fallback
            r, _, _ = image.split()
            return r
        case "RGBA":
            if channel == "red":
                r, _, _, _ = image.split()
                return r
            if channel == "green":
                _, g, _, _ = image.split()
                return g
            if channel == "blue":
                _, _, b, _ = image.split()
                return b
            if channel == "alpha":
                _, _, _, a = image.split()
                return a
            # Fallback to red channel
            r, _, _, _ = image.split()
            return r
        case "L":
            # Grayscale image - use directly
            return image
        case "LA":
            if channel == "alpha":
                _, a = image.split()
                return a
            # Use grayscale channel
            gray, _ = image.split()
            return gray
        case _:
            msg = f"Unsupported {context_name} mode: {image.mode}"
            raise ValueError(msg)


# New functions for DisplayImageGrid


def create_placeholder_image(width: int, height: int, background_color: str, transparent_bg: bool) -> Image.Image:
    """Create a placeholder image with specified dimensions and background."""
    if transparent_bg:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    else:
        # Convert hex color to RGB
        background_color = background_color.removeprefix("#")
        rgb_color = tuple(int(background_color[i : i + 2], 16) for i in (0, 2, 4))
        image = Image.new("RGB", (width, height), rgb_color)

    return image


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


def create_grid_layout(
    images: list,
    columns: int,
    output_image_width: int,
    spacing: int,
    background_color: str,
    border_radius: int,
    crop_to_fit: bool,
    transparent_bg: bool,
) -> Image.Image:
    """Create a uniform grid layout of images."""
    if not images:
        return create_placeholder_image(400, 300, background_color, transparent_bg)

    # Load and process images
    pil_images = []
    for img_item in images:
        try:
            url = extract_image_url(img_item)
            pil_img = load_pil_from_url(url)
            pil_images.append(pil_img)
        except Exception as e:
            # Skip invalid images
            logger.debug(f"Skipping invalid image: {e}")
            continue

    if not pil_images:
        return create_placeholder_image(400, 300, background_color, transparent_bg)

    # Calculate grid dimensions
    rows = (len(pil_images) + columns - 1) // columns
    cell_width = (output_image_width - spacing * (columns + 1)) // columns
    cell_height = cell_width  # Square cells for grid layout

    # Create background
    total_width = cell_width * columns + spacing * (columns + 1)
    total_height = cell_height * rows + spacing * (rows + 1)

    if transparent_bg:
        grid_image = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 0))
    else:
        background_color = background_color.removeprefix("#")
        rgb_color = tuple(int(background_color[i : i + 2], 16) for i in (0, 2, 4))
        grid_image = Image.new("RGB", (total_width, total_height), rgb_color)

    # Place images in grid
    for idx, img in enumerate(pil_images):
        row = idx // columns
        col = idx % columns

        # Resize image to fit cell
        if crop_to_fit:
            # Crop to square
            img_resized = img.copy()
            img_resized.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)

            # Center the image
            x_offset = col * cell_width + spacing + (cell_width - img_resized.width) // 2
            y_offset = row * cell_height + spacing + (cell_height - img_resized.height) // 2
        else:
            # Scale to fit
            img_resized = img.copy()
            img_resized.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)

            x_offset = col * cell_width + spacing + (cell_width - img_resized.width) // 2
            y_offset = row * cell_height + spacing + (cell_height - img_resized.height) // 2

        # Apply border radius if specified
        if border_radius > 0:
            img_resized = apply_border_radius(img_resized, border_radius)

        grid_image.paste(img_resized, (x_offset, y_offset), img_resized if img_resized.mode == "RGBA" else None)

    return grid_image


def create_masonry_layout(
    images: list,
    columns: int,
    output_image_width: int,
    spacing: int,
    background_color: str,
    border_radius: int,
    crop_to_fit: bool,  # noqa: ARG001
    transparent_bg: bool,
) -> Image.Image:
    """Create a masonry layout with variable height columns."""
    if not images:
        return create_placeholder_image(400, 300, background_color, transparent_bg)

    # Load and process images
    pil_images = []
    for img_item in images:
        try:
            url = extract_image_url(img_item)
            pil_img = load_pil_from_url(url)
            pil_images.append(pil_img)
        except Exception as e:
            # Skip invalid images
            logger.debug(f"Skipping invalid image: {e}")
            continue

    if not pil_images:
        return create_placeholder_image(400, 300, background_color, transparent_bg)

    # Calculate column width
    column_width = (output_image_width - spacing * (columns + 1)) // columns

    # Distribute images across columns
    columns_content = [[] for _ in range(columns)]
    column_heights = [0] * columns

    for _idx, img in enumerate(pil_images):
        # Find shortest column
        shortest_col = column_heights.index(min(column_heights))
        columns_content[shortest_col].append(img)

        # Calculate height for this image
        aspect_ratio = img.width / img.height
        img_height = int(column_width / aspect_ratio)
        column_heights[shortest_col] += img_height + spacing

    # Create background
    total_height = max(column_heights) + spacing
    if transparent_bg:
        grid_image = Image.new("RGBA", (output_image_width, total_height), (0, 0, 0, 0))
    else:
        background_color = background_color.removeprefix("#")
        rgb_color = tuple(int(background_color[i : i + 2], 16) for i in (0, 2, 4))
        grid_image = Image.new("RGB", (output_image_width, total_height), rgb_color)

    # Place images in columns
    for col_idx, column_images in enumerate(columns_content):
        x_offset = col_idx * column_width + spacing * (col_idx + 1)
        y_offset = spacing

        for img in column_images:
            # Resize image to fit column width
            img_resized = img.copy()
            aspect_ratio = img.width / img.height
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

    # Draw rounded rectangle mask
    from PIL import ImageDraw

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
