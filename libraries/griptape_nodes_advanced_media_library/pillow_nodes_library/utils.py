import io
import uuid

import PIL.Image
import PIL.ImageOps
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL.Image import Image


def image_artifact_to_pil(image_artifact: ImageArtifact) -> Image:
    """Converts Griptape ImageArtifact to Pillow Image."""
    return PIL.Image.open(io.BytesIO(image_artifact.value))


def pil_to_image_artifact(pil_image: Image) -> ImageUrlArtifact:
    """Converts Pillow Image to Griptape ImageArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    image_io = io.BytesIO()
    pil_image.save(image_io, "PNG")
    image_bytes = image_io.getvalue()
    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, f"{uuid.uuid4()}.png")
    return ImageUrlArtifact(value=url)


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
