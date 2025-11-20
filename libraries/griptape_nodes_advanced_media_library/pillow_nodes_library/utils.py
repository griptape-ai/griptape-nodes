import io
import uuid

import PIL.Image
import PIL.ImageOps
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL.Image import Image


def image_artifact_to_pil(image_artifact: ImageArtifact) -> Image:
    """Converts Griptape ImageArtifact to Pillow Image."""
    return PIL.Image.open(io.BytesIO(image_artifact.value))


def pil_to_image_artifact(pil_image: Image, directory_path: str = "") -> ImageUrlArtifact:
    """Converts Pillow Image to Griptape ImageArtifact."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    image_io = io.BytesIO()
    pil_image.save(image_io, "PNG")
    image_bytes = image_io.getvalue()

    if directory_path:
        # Perform cleanup if needed before saving new file
        cleanup_enabled = GriptapeNodes.ConfigManager().get_config_value(
            "advanced_media_library.enable_directory_cleanup"
        )
        if cleanup_enabled:
            static_files_directory = GriptapeNodes.ConfigManager().get_config_value(
                "static_files_directory", default="staticfiles"
            )
            path = GriptapeNodes.ConfigManager().workspace_path / static_files_directory / directory_path

            max_size_gb = GriptapeNodes.ConfigManager().get_config_value("advanced_media_library.max_directory_size_gb")
            GriptapeNodes.OSManager().cleanup_directory_if_needed(full_directory_path=path, max_size_gb=max_size_gb)

        # Now set the file name.
        filename = f"{directory_path}/{uuid.uuid4()}.png"
    else:
        # No directory prefix - direct storage
        filename = f"{uuid.uuid4()}.png"

    url = GriptapeNodes.StaticFilesManager().save_static_file(image_bytes, filename)
    return ImageUrlArtifact(url)


def video_url_artifact_to_pil_images(video_artifact: VideoUrlArtifact) -> list[Image]:
    """Converts VideoUrlArtifact to a list of PIL Images.

    Args:
        video_artifact: VideoUrlArtifact containing the video URL

    Returns:
        List of PIL Images, one for each frame in the video
    """
    import diffusers.utils  # type: ignore[reportMissingImports]

    # Use diffusers' load_video utility to convert video URL to PIL frames
    return diffusers.utils.loading_utils.load_video(video_artifact.value)


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
