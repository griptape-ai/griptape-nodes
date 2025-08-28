from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class ConvertGrayscale(BaseImageProcessor):
    """Convert an image to grayscale using PIL."""

    def _setup_custom_parameters(self) -> None:
        """No custom parameters needed for grayscale conversion."""

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "Converting image to grayscale"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Convert the image to grayscale."""
        # Convert to grayscale
        grayscale_image = image.convert("L")

        return grayscale_image

    def _get_custom_parameters(self) -> dict:
        """No custom parameters for grayscale conversion."""
        return {}

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        return "_grayscale"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """No custom parameters to validate for grayscale conversion."""
        return None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Run processing after input image is set for real-time feedback."""
        # Process immediately when input image is set
        if parameter.name == "input_image" and value is not None:
            try:
                # Run the processing to update the output
                self.process()
            except Exception as e:
                # Log error but don't crash the UI
                from griptape_nodes.retained_mode.griptape_nodes import logger

                logger.warning(f"{self.name}: Error during live grayscale conversion: {e}")

        return super().after_value_set(parameter, value)
