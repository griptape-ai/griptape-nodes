import io

from griptape.artifacts import ImageArtifact
from PIL import Image


def image_artifact_to_pil(image_artifact: ImageArtifact) -> Image:
    """Converts Griptape ImageArtifact to Pillow Image."""
    return Image.open(io.BytesIO(image_artifact.value))


def pil_to_image_artifact(pil_image: Image) -> ImageArtifact:
    """Converts Pillow Image to Griptape ImageArtifact."""
    image_io = io.BytesIO()
    pil_image.save(image_io, "PNG")
    image_bytes = image_io.getvalue()
    width, height = pil_image.size
    return ImageArtifact(
        value=image_bytes,
        format="image/png",
        width=width,
        height=height,
    )
