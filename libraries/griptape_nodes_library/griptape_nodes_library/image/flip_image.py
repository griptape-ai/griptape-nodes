from typing import Any

from PIL import Image, ImageOps

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class FlipImage(BaseImageProcessor):
    """Flip image horizontally or vertically."""

    def _setup_custom_parameters(self) -> None:
        """Setup flip-specific parameters."""
        with ParameterGroup(name="flip_settings", ui_options={"collapsed": False}) as flip_group:
            # Flip direction parameter
            direction_parameter = Parameter(
                name="direction",
                type="str",
                default_value="horizontal",
                tooltip="Flip direction: horizontal, vertical, or both",
            )
            direction_parameter.add_trait(Options(choices=["horizontal", "vertical", "both"]))
            self.add_parameter(direction_parameter)

        self.add_node_element(flip_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when connected or when flip parameters change."""
        if parameter.name == "input_image" and value is not None:
            # Process the image immediately when connected
            self._process_image_immediately(value)
        elif parameter.name == "direction":
            # Re-process when direction changes
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                self._process_image_immediately(input_image)
        return super().after_value_set(parameter, value)

    def _process_image_immediately(self, image_value: Any) -> None:
        """Process image immediately for live preview."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                image_artifact = dict_to_image_url_artifact(image_value)
            else:
                image_artifact = image_value

            # Load PIL image
            pil_image = load_pil_from_url(image_artifact.value)

            # Get current direction
            direction = self.get_parameter_value("direction") or "horizontal"

            # Process with current flip settings
            processed_image = self._process_image(pil_image, direction=direction)

            # Save and set output with proper filename
            filename = self._generate_processed_image_filename("png")
            output_artifact = save_pil_image_with_named_filename(processed_image, filename, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            # Log error but don't fail the node
            logger.warning(f"{self.name}: Live preview failed: {e}")

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "image flipping"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image by flipping it."""
        direction = kwargs.get("direction", "horizontal")

        logger.debug(f"{self.name}: Flipping image with direction={direction}")

        # Apply flip based on direction
        if direction == "horizontal":
            pil_image = ImageOps.mirror(pil_image)
        elif direction == "vertical":
            pil_image = ImageOps.flip(pil_image)
        elif direction == "both":
            pil_image = ImageOps.mirror(pil_image)
            pil_image = ImageOps.flip(pil_image)

        return pil_image

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate flip parameters."""
        exceptions = []

        direction = self.get_parameter_value("direction")
        valid_choices = ["horizontal", "vertical", "both"]
        if direction is not None and direction not in valid_choices:
            msg = f"{self.name} - Direction must be one of {valid_choices}, got {direction}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, str]:
        """Get flip parameters."""
        return {
            "direction": self.get_parameter_value("direction"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        direction = kwargs.get("direction", "horizontal")
        return f"_flipped_{direction}"
