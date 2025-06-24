import io
import uuid

import PIL.Image
import PIL.ImageOps
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.loaders import ImageLoader
from PIL.Image import Image


def image_artifact_to_pil(image_artifact: ImageArtifact | ImageUrlArtifact | dict) -> Image:
    """Converts Griptape ImageArtifact to Pillow Image.

    Args:
        image_artifact: Either an ImageArtifact/ImageUrlArtifact object or a dictionary representation of one

    Returns:
        PIL Image object

    Raises:
        ValueError: If the image_artifact is invalid or missing required data
    """
    # Handle dictionary case - reconstruct proper artifact
    if isinstance(image_artifact, dict):
        value = image_artifact.get("value")
        if not isinstance(value, str):
            msg = f"Invalid image data format - expected string value: {value}"
            raise TypeError(msg)

        # If it's a URL artifact, load it properly
        if image_artifact.get("type") == "ImageUrlArtifact":
            url_artifact = ImageUrlArtifact(value=value)
            try:
                image_bytes = url_artifact.to_bytes()
                image_artifact = ImageLoader().parse(image_bytes)
            except Exception as e:
                msg = f"Failed to load image from URL: {e}"
                raise TypeError(msg) from e
        else:
            # For raw image data, parse it properly
            try:
                image_artifact = ImageLoader().parse(value.encode("utf-8"))
            except Exception as e:
                msg = f"Failed to parse image data: {e}"
                raise TypeError(msg) from e

    # Handle URL artifacts
    if isinstance(image_artifact, ImageUrlArtifact):
        try:
            image_bytes = image_artifact.to_bytes()
            image_artifact = ImageLoader().parse(image_bytes)
        except Exception as e:
            msg = f"Failed to load image from URL: {e}"
            raise TypeError(msg) from e

    if not isinstance(image_artifact, ImageArtifact):
        msg = f"Expected ImageArtifact after processing, got {type(image_artifact)}"
        raise TypeError(msg)

    return PIL.Image.open(io.BytesIO(image_artifact.value))


def pil_to_image_artifact(pil_image: Image) -> ImageUrlArtifact:
    """Converts Pillow Image to Griptape ImageArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    image_io = io.BytesIO()
    pil_image.save(image_io, "PNG")
    image_bytes = image_io.getvalue()
    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.png")
    return ImageUrlArtifact(url)


def pad_mirror(image: Image, target_size: tuple[int, int]) -> Image:
    """Expand an image to the target size using repeated mirrored tiling.

    Parameters:
    - image: Input Pillow Image
    - target_size: (new_width, new_height)

    Returns:
    - A new Image of size target_size, filled with mirrored tiles of the original
    """
    orig_w, orig_h = image.size
    target_w, target_h = target_size

    # Create the 2x2 mirrored variants
    tiles = [
        [image, PIL.ImageOps.mirror(image)],
        [PIL.ImageOps.flip(image), PIL.ImageOps.mirror(PIL.ImageOps.flip(image))],
    ]

    # Compute how many tiles are needed horizontally and vertically
    tiles_x = (target_w + orig_w - 1) // orig_w
    tiles_y = (target_h + orig_h - 1) // orig_h

    # Create blank output canvas
    new_img = PIL.Image.new(image.mode, (target_w, target_h))

    for y in range(tiles_y):
        for x in range(tiles_x):
            tile = tiles[y % 2][x % 2]
            new_img.paste(tile, (x * orig_w, y * orig_h))

    # Crop to exact target size (if overshot)
    return new_img.crop((0, 0, target_w, target_h))
