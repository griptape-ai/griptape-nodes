from typing import Any

from PIL import Image, ImageEnhance

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class GrayscaleImage(BaseImageProcessor):
    """Convert image to grayscale using PIL's ImageEnhance."""

    def _setup_custom_parameters(self) -> None:
        """Setup brightness/contrast-specific parameters."""

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when connected or when EQ parameters change."""
        if parameter.name == "input_image" and value is not None:
            # Process the image immediately when connected
            self._process_image_immediately(value)
        return super().after_value_set(parameter, value)

    def _process_image_immediately(self, image_value: Any) -> None:
        """Process image immediately for live preview."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

                image_artifact = dict_to_image_url_artifact(image_value)
            else:
                image_artifact = image_value

            # Load PIL image
            pil_image = load_pil_from_url(image_artifact.value)

            # Process with current EQ settings
            processed_image = self._process_image(pil_image)

            # Save and set output with proper filename
            # Generate a meaningful filename with processing parameters
            filename = self._generate_processed_image_filename("png")
            output_artifact = save_pil_image_with_named_filename(processed_image, filename, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            # Log error but don't fail the node
            logger.warning(f"{self.name}: Live preview failed: {e}")

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "grayscale conversion"

    def _process_image(self, pil_image: Image.Image) -> Image.Image:
        """Process the PIL image by converting to grayscale."""
        saturation = 0

        logger.debug(f"{self.name}: Processing image with saturation={saturation}")

        # Apply saturation adjustment
        enhancer = ImageEnhance.Color(pil_image)
        pil_image = enhancer.enhance(saturation)

        return pil_image

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters."""
        return None

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_grayscale"
