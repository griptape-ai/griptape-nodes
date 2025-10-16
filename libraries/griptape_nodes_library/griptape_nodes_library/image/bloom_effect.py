from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class BloomEffect(BaseImageProcessor):
    """Apply a bloom/glow effect to images with configurable intensity and radius."""

    # Bloom amount constants
    MIN_BLOOM_AMOUNT = 0.0
    MAX_BLOOM_AMOUNT = 2.0
    DEFAULT_BLOOM_AMOUNT = 0.5

    # Bloom radius constants
    MIN_BLOOM_RADIUS = 1
    MAX_BLOOM_RADIUS = 20
    DEFAULT_BLOOM_RADIUS = 5

    def _setup_custom_parameters(self) -> None:
        """Setup bloom-specific parameters."""
        with ParameterGroup(name="bloom_settings", ui_options={"collapsed": False}) as bloom_group:
            # Bloom amount parameter
            bloom_amount_param = Parameter(
                name="bloom_amount",
                type="float",
                default_value=self.DEFAULT_BLOOM_AMOUNT,
                tooltip=f"Bloom intensity ({self.MIN_BLOOM_AMOUNT}-{self.MAX_BLOOM_AMOUNT}, 0.0 = no effect, 2.0 = maximum glow)",
            )
            bloom_amount_param.add_trait(Slider(min_val=self.MIN_BLOOM_AMOUNT, max_val=self.MAX_BLOOM_AMOUNT))
            self.add_parameter(bloom_amount_param)

            # Bloom radius parameter
            bloom_radius_param = Parameter(
                name="bloom_radius",
                type="int",
                default_value=self.DEFAULT_BLOOM_RADIUS,
                tooltip=f"Bloom radius in pixels ({self.MIN_BLOOM_RADIUS}-{self.MAX_BLOOM_RADIUS}, higher = softer glow)",
            )
            bloom_radius_param.add_trait(Slider(min_val=self.MIN_BLOOM_RADIUS, max_val=self.MAX_BLOOM_RADIUS))
            self.add_parameter(bloom_radius_param)

        self.add_node_element(bloom_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when connected or when bloom parameters change."""
        if parameter.name == "input_image" and value is not None:
            # Process the image immediately when connected
            self._process_image_immediately(value)
        elif parameter.name in ["bloom_amount", "bloom_radius"]:
            # Process the image when bloom parameters change (for live preview)
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

            # Process with current bloom settings
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
        return "image bloom effect"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image by applying bloom effect."""
        bloom_amount = kwargs.get("bloom_amount", self.DEFAULT_BLOOM_AMOUNT)
        bloom_radius = kwargs.get("bloom_radius", self.DEFAULT_BLOOM_RADIUS)

        if bloom_amount <= 0.0:
            return pil_image  # No bloom effect

        # Convert to RGB if needed (bloom works best with RGB)
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        # Create a brightened version for bloom
        brightened = ImageEnhance.Brightness(pil_image).enhance(1.0 + bloom_amount)

        # Apply Gaussian blur to create the bloom effect
        bloomed = brightened.filter(ImageFilter.GaussianBlur(radius=bloom_radius))

        # Blend the original image with the bloomed version
        # Use a weighted blend based on bloom amount
        blend_factor = min(bloom_amount, 1.0)  # Cap at 1.0 for reasonable blending

        # Create the final image by blending
        result = Image.blend(pil_image, bloomed, blend_factor)

        return result

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate bloom parameters."""
        exceptions = []

        bloom_amount = self.get_parameter_value("bloom_amount")
        if bloom_amount is not None and (bloom_amount < self.MIN_BLOOM_AMOUNT or bloom_amount > self.MAX_BLOOM_AMOUNT):
            msg = f"{self.name} - Bloom amount must be between {self.MIN_BLOOM_AMOUNT} and {self.MAX_BLOOM_AMOUNT}, got {bloom_amount}"
            exceptions.append(ValueError(msg))

        bloom_radius = self.get_parameter_value("bloom_radius")
        if bloom_radius is not None and (bloom_radius < self.MIN_BLOOM_RADIUS or bloom_radius > self.MAX_BLOOM_RADIUS):
            msg = f"{self.name} - Bloom radius must be between {self.MIN_BLOOM_RADIUS} and {self.MAX_BLOOM_RADIUS}, got {bloom_radius}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get bloom parameters."""
        return {
            "bloom_amount": self.get_parameter_value("bloom_amount"),
            "bloom_radius": self.get_parameter_value("bloom_radius"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_bloom"
