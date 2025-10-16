from typing import Any

from PIL import Image, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class GaussianBlurImage(BaseImageProcessor):
    """Apply Gaussian blur to an image using PIL's ImageFilter."""

    # Radius constants
    MIN_RADIUS = 0.0
    MAX_RADIUS = 50.0
    DEFAULT_RADIUS = 5.0

    def _setup_custom_parameters(self) -> None:
        """Setup blur-specific parameters."""
        with ParameterGroup(name="blur_settings", ui_options={"collapsed": False}) as blur_group:
            # Radius parameter
            radius_param = Parameter(
                name="radius",
                type="float",
                default_value=self.DEFAULT_RADIUS,
                tooltip=f"Blur radius ({self.MIN_RADIUS}-{self.MAX_RADIUS}, higher values create more blur)",
            )
            radius_param.add_trait(Slider(min_val=self.MIN_RADIUS, max_val=self.MAX_RADIUS))
            self.add_parameter(radius_param)

        self.add_node_element(blur_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when connected or when blur parameters change."""
        if parameter.name == "input_image" and value is not None:
            # Process the image immediately when connected
            self._process_image_immediately(value)
        elif parameter.name == "radius":
            # Process the image when blur parameters change (for live preview)
            image_value = self.get_parameter_value("input_image")
            if image_value is not None:
                self._process_image_immediately(image_value)
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

            # Process with current blur settings
            processed_image = self._process_image(pil_image, **self._get_custom_parameters())

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
        return "Gaussian blur"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image by applying Gaussian blur."""
        radius = kwargs.get("radius", self.DEFAULT_RADIUS)

        # Debug logging
        logger.debug(f"{self.name}: Processing image with blur radius={radius}")

        # Apply Gaussian blur
        if radius > 0:
            blurred_image = pil_image.filter(ImageFilter.GaussianBlur(radius=radius))
            return blurred_image
        # If radius is 0, return original image (no blur)
        return pil_image

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate blur parameters."""
        exceptions = []

        radius = self.get_parameter_value("radius")
        if radius is not None and (radius < self.MIN_RADIUS or radius > self.MAX_RADIUS):
            msg = f"{self.name} - Radius must be between {self.MIN_RADIUS} and {self.MAX_RADIUS}, got {radius}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get blur parameters."""
        return {
            "radius": self.get_parameter_value("radius"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        radius = kwargs.get("radius", self.DEFAULT_RADIUS)
        return f"_blur_{radius:.1f}"
