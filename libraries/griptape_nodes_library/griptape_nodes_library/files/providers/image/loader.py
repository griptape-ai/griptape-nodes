from pathlib import Path
from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_load_provider import ArtifactLoadProvider
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    extract_channel_from_image,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class ImageLoadProvider(ArtifactLoadProvider):
    """Provider for loading and processing image files."""

    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

    @property
    def provider_name(self) -> str:
        return "Image"

    @property
    def artifact_type(self) -> str:
        return "ImageUrlArtifact"

    @property
    def supported_extensions(self) -> set[str]:
        return self.SUPPORTED_EXTENSIONS

    @property
    def url_content_type_prefix(self) -> str:
        return "image/"

    @property
    def default_extension(self) -> str:
        return "png"

    def can_handle_file(self, file_path: Path) -> bool:
        """Check if this provider can handle the given file path."""
        return file_path.suffix.lower() in self.supported_extensions

    def can_handle_url(self, url: str) -> bool:
        """Check if this provider can handle content from the given URL."""
        # Basic check - could be enhanced with HEAD request to check content-type
        url_lower = url.lower()
        for ext in self.supported_extensions:
            if ext in url_lower:
                return True
        return False

    def get_additional_parameters(self) -> list[Parameter]:
        """Get image-specific parameters."""
        # Mask channel parameter
        channel_param = Parameter(
            name="mask_channel",
            type="str",
            tooltip="Channel to extract as mask (red, green, blue, or alpha).",
            default_value="alpha",
            ui_options={"hide": True},
        )
        channel_param.add_trait(Options(choices=["red", "green", "blue", "alpha"]))

        # Output mask parameter
        output_mask_param = Parameter(
            name="output_mask",
            type="ImageUrlArtifact",
            tooltip="The Mask for the image",
            ui_options={"expander": True, "hide": True},
            allowed_modes={ParameterMode.OUTPUT},
        )

        return [channel_param, output_mask_param]

    def create_artifact_from_dict(self, artifact_dict: dict[str, Any]) -> ImageUrlArtifact:
        """Convert a dictionary to ImageUrlArtifact."""
        return dict_to_image_url_artifact(artifact_dict)

    def create_artifact_from_url(self, url: str) -> ImageUrlArtifact:
        """Create an ImageUrlArtifact from a URL."""
        return ImageUrlArtifact(value=url)

    def validate_artifact_loadable(self, artifact: Any) -> None:
        """Validate that the image artifact can actually be loaded."""
        if artifact is None:
            msg = "Attempted to validate image artifact. Failed due to artifact is None"
            raise RuntimeError(msg)

        # Get URL from artifact
        url = self.extract_url_from_artifact(artifact)
        if not url:
            msg = (
                f"Attempted to validate image artifact of type '{type(artifact).__name__}'. "
                f"Failed due to no URL found in artifact"
            )
            raise RuntimeError(msg)

        try:
            # Attempt to load the image to verify it's valid
            load_pil_from_url(url)
        except Exception as e:
            msg = f"Attempted to validate image artifact with URL '{url}'. Failed due to image verification error: {e}"
            raise RuntimeError(msg) from e

    def extract_url_from_artifact(self, artifact_value: Any) -> str | None:
        """Extract URL from image parameter value."""
        if not artifact_value:
            return None

        match artifact_value:
            # Handle dictionary format
            case dict():
                return artifact_value.get("value")
            # Handle ImageUrlArtifact objects
            case _ if isinstance(artifact_value, ImageUrlArtifact):
                return artifact_value.value
            # Handle raw strings
            case str():
                return artifact_value
            case _:
                return None

    def process_additional_parameters(self, node: Any, artifact: Any) -> None:
        """Process image-specific parameters after artifact is loaded."""
        # Extract mask if both image and mask_channel are available
        try:
            mask_channel = node.get_parameter_value("mask_channel")
            if artifact and mask_channel:
                self._extract_mask_if_possible(node, artifact, mask_channel)
        except Exception as e:
            logger.warning(
                f"Attempted to process additional image parameters for node '{node.name}'. Failed due to {e}"
            )

    def get_priority_score(self, file_path: Path) -> int:
        """Get priority score for handling this file."""
        extension = file_path.suffix.lower()

        # Higher priority for common image formats
        if extension in {".png", ".jpg", ".jpeg"}:
            return 100
        if extension in {".webp", ".gif"}:
            return 90
        if extension == ".svg":
            return 80

        return 0

    def _extract_mask_if_possible(self, node: Any, image_artifact: Any, mask_channel: str) -> None:
        """Extract mask from the loaded image if both image and channel are available."""
        if not image_artifact or not mask_channel:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(image_artifact, dict):
            image_artifact = self.create_artifact_from_dict(image_artifact)

        self._extract_channel_as_mask(node, image_artifact, mask_channel)

    def _extract_channel_as_mask(self, node: Any, image_artifact: ImageUrlArtifact, channel: str) -> None:
        """Extract a channel from the input image and set as mask output."""
        try:
            # Load image
            image_pil = load_pil_from_url(image_artifact.value)

            # Extract the specified channel as mask
            mask = extract_channel_from_image(image_pil, channel, "image")

            # Save output mask and create URL artifact with proper filename
            filename = generate_filename(
                node_name=node.name,
                suffix="_load_mask",
                extension="png",
            )
            output_artifact = save_pil_image_with_named_filename(mask, filename, "PNG")

            # Set the output mask parameter
            try:
                node.set_parameter_value("output_mask", output_artifact)
                node.publish_update_to_parameter("output_mask", output_artifact)
            except Exception as e:
                logger.warning(f"Attempted to set output_mask parameter on node '{node.name}'. Failed due to {e}")

        except Exception as e:
            logger.warning(
                f"Attempted to extract mask from image on node '{node.name}' using channel '{channel}'. "
                f"Failed due to {e}"
            )
