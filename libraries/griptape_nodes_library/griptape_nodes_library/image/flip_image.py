from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class FlipImage(BaseImageProcessor):
    """Flip an image horizontally or vertically using PIL."""

    # Flip options
    FLIP_OPTIONS = {
        "horizontal": "Flip horizontally (left to right)",
        "vertical": "Flip vertically (top to bottom)",
        "both": "Flip both horizontally and vertically",
    }

    def _setup_custom_parameters(self) -> None:
        """Setup flip parameters."""
        # Flip direction parameter
        flip_direction_param = Parameter(
            name="flip_direction",
            type="str",
            default_value="horizontal",
            tooltip="Direction to flip the image",
        )
        flip_direction_param.add_trait(Options(choices=list(self.FLIP_OPTIONS.keys())))
        self.add_parameter(flip_direction_param)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        flip_direction = self.get_parameter_value("flip_direction") or "horizontal"
        return f"Flipping image {flip_direction}"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Flip the image."""
        flip_direction = kwargs.get("flip_direction", "horizontal")

        if flip_direction == "horizontal":
            # Flip horizontally
            flipped_image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif flip_direction == "vertical":
            # Flip vertically
            flipped_image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif flip_direction == "both":
            # Flip both horizontally and vertically
            flipped_image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        else:
            # Default to horizontal flip
            flipped_image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        return flipped_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get flip parameters."""
        return {
            "flip_direction": self.get_parameter_value("flip_direction") or "horizontal",
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        flip_direction = kwargs.get("flip_direction", "horizontal")
        return f"_flipped_{flip_direction}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate flip parameters."""
        # No validation needed for flip direction as it's constrained by options
        return None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Run processing after parameter values are set for real-time feedback."""
        # Only process if we have an input image and the parameter is flip direction
        if parameter.name == "flip_direction":
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                try:
                    # Run the processing to update the output
                    self.process()
                except Exception as e:
                    # Log error but don't crash the UI
                    from griptape_nodes.retained_mode.griptape_nodes import logger

                    logger.warning(f"{self.name}: Error during live flip: {e}")

        return super().after_value_set(parameter, value)
