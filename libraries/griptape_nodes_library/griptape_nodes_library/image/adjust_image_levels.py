from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class AdjustImageLevels(BaseImageProcessor):
    """Adjust image levels similar to Photoshop's levels adjustment."""

    # Input levels constants (0-255)
    MIN_INPUT_LEVEL = 0
    MAX_INPUT_LEVEL = 255
    DEFAULT_SHADOWS = 0
    DEFAULT_MIDTONES = 1.0
    DEFAULT_HIGHLIGHTS = 255

    # Output levels constants (0-255)
    MIN_OUTPUT_LEVEL = 0
    MAX_OUTPUT_LEVEL = 255
    DEFAULT_OUTPUT_SHADOWS = 0
    DEFAULT_OUTPUT_HIGHLIGHTS = 255

    # Internal constants
    MAX_PIXEL_VALUE = 255

    def _setup_custom_parameters(self) -> None:
        """Setup levels-specific parameters."""
        # Input levels group
        with ParameterGroup(name="input_levels", ui_options={"collapsed": False}):
            # Shadows parameter
            shadows_param = Parameter(
                name="shadows",
                type="int",
                default_value=self.DEFAULT_SHADOWS,
                tooltip="Input shadows level (0-255). Pixels below this value will be mapped to output shadows.",
            )
            shadows_param.add_trait(Slider(min_val=self.MIN_INPUT_LEVEL, max_val=self.MAX_INPUT_LEVEL))
            self.add_parameter(shadows_param)

            # Midtones parameter
            midtones_param = Parameter(
                name="midtones",
                type="float",
                default_value=self.DEFAULT_MIDTONES,
                tooltip="Midtones adjustment (0.1-10.0). Values < 1.0 lighten midtones, > 1.0 darken midtones.",
            )
            midtones_param.add_trait(Slider(min_val=0.1, max_val=10.0))
            self.add_parameter(midtones_param)

            # Highlights parameter
            highlights_param = Parameter(
                name="highlights",
                type="int",
                default_value=self.DEFAULT_HIGHLIGHTS,
                tooltip="Input highlights level (0-255). Pixels above this value will be mapped to output highlights.",
            )
            highlights_param.add_trait(Slider(min_val=self.MIN_INPUT_LEVEL, max_val=self.MAX_INPUT_LEVEL))
            self.add_parameter(highlights_param)

        # Output levels group
        with ParameterGroup(name="output_levels", ui_options={"collapsed": False}):
            # Output shadows parameter
            output_shadows_param = Parameter(
                name="output_shadows",
                type="int",
                default_value=self.DEFAULT_OUTPUT_SHADOWS,
                tooltip="Output shadows level (0-255). Input shadows will be mapped to this value.",
            )
            output_shadows_param.add_trait(Slider(min_val=self.MIN_OUTPUT_LEVEL, max_val=self.MAX_OUTPUT_LEVEL))
            self.add_parameter(output_shadows_param)

            # Output highlights parameter
            output_highlights_param = Parameter(
                name="output_highlights",
                type="int",
                default_value=self.DEFAULT_OUTPUT_HIGHLIGHTS,
                tooltip="Output highlights level (0-255). Input highlights will be mapped to this value.",
            )
            output_highlights_param.add_trait(Slider(min_val=self.MIN_OUTPUT_LEVEL, max_val=self.MAX_OUTPUT_LEVEL))
            self.add_parameter(output_highlights_param)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle live preview when parameters change."""
        if parameter.name in ["shadows", "midtones", "highlights", "output_shadows", "output_highlights"]:
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

            # Process with current levels settings
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

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Apply levels adjustment to the image."""
        shadows = int(kwargs.get("shadows", self.DEFAULT_SHADOWS))
        midtones = float(kwargs.get("midtones", self.DEFAULT_MIDTONES))
        highlights = int(kwargs.get("highlights", self.DEFAULT_HIGHLIGHTS))
        output_shadows = int(kwargs.get("output_shadows", self.DEFAULT_OUTPUT_SHADOWS))
        output_highlights = int(kwargs.get("output_highlights", self.DEFAULT_OUTPUT_HIGHLIGHTS))

        # Debug logging
        logger.debug(
            f"{self.name}: Processing image with shadows={shadows}, midtones={midtones}, "
            f"highlights={highlights}, output_shadows={output_shadows}, output_highlights={output_highlights}"
        )

        # Validate input levels
        if shadows >= highlights:
            logger.warning(f"{self.name}: Shadows ({shadows}) must be less than highlights ({highlights})")
            shadows = min(shadows, highlights - 1)

        # Create levels lookup table
        levels_table = self._create_levels_table(shadows, midtones, highlights, output_shadows, output_highlights)

        # Apply levels adjustment
        if pil_image.mode == "RGBA":
            # Handle RGBA images by processing RGB channels and preserving alpha
            rgb_image = pil_image.convert("RGB")
            combined_table = levels_table + levels_table + levels_table
            adjusted_rgb = rgb_image.point(combined_table)
            adjusted_image = adjusted_rgb.convert("RGBA")
            original_alpha = pil_image.getchannel("A")
            adjusted_image.putalpha(original_alpha)
            return adjusted_image
        if pil_image.mode == "RGB":
            combined_table = levels_table + levels_table + levels_table
            return pil_image.point(combined_table)
        if pil_image.mode == "L":
            return pil_image.point(levels_table)
        # Convert other modes to RGB, process, then convert back
        rgb_image = pil_image.convert("RGB")
        combined_table = levels_table + levels_table + levels_table
        adjusted_rgb = rgb_image.point(combined_table)
        return adjusted_rgb.convert(pil_image.mode)

    def _create_levels_table(
        self,
        shadows: int,
        midtones: float,
        highlights: int,
        output_shadows: int,
        output_highlights: int,
    ) -> list[int]:
        """Create a levels adjustment lookup table."""
        table = []

        for i in range(256):
            # Step 1: Apply input levels (shadows and highlights clipping)
            if i <= shadows:
                # Map everything below shadows to 0
                input_value = 0
            elif i >= highlights:
                # Map everything above highlights to max value
                input_value = self.MAX_PIXEL_VALUE
            else:
                # Linear mapping between shadows and highlights
                input_value = int(self.MAX_PIXEL_VALUE * (i - shadows) / (highlights - shadows))

            # Step 2: Apply midtones (gamma) adjustment
            if input_value == 0:
                gamma_value = 0
            elif input_value == self.MAX_PIXEL_VALUE:
                gamma_value = self.MAX_PIXEL_VALUE
            else:
                # Apply gamma correction: output = max * (input/max)^(1/gamma)
                gamma_value = int(self.MAX_PIXEL_VALUE * pow(input_value / self.MAX_PIXEL_VALUE, 1.0 / midtones))

            # Step 3: Apply output levels mapping
            if gamma_value == 0:
                output_value = output_shadows
            elif gamma_value == self.MAX_PIXEL_VALUE:
                output_value = output_highlights
            else:
                # Linear mapping from 0-max to output_shadows-output_highlights
                output_value = int(
                    output_shadows + (output_highlights - output_shadows) * (gamma_value / self.MAX_PIXEL_VALUE)
                )

            # Clamp to valid range
            table.append(max(0, min(self.MAX_PIXEL_VALUE, output_value)))

        return table

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for this processor."""
        return {
            "shadows": self.get_parameter_value("shadows"),
            "midtones": self.get_parameter_value("midtones"),
            "highlights": self.get_parameter_value("highlights"),
            "output_shadows": self.get_parameter_value("output_shadows"),
            "output_highlights": self.get_parameter_value("output_highlights"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_levels"

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "image levels adjustment (shadows, midtones, highlights, output levels)"
