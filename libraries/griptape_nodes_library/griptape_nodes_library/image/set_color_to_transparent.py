"""SetColorToTransparent node for replacing a specific color with transparency.

This node takes an input image and replaces pixels matching a specified color
(within a tolerance range) with transparent pixels, outputting a PNG image.
"""

from typing import Any

import numpy as np
from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    parse_hex_color,
    save_pil_image_with_named_filename,
)


class SetColorToTransparent(DataNode):
    """Replace a specific color in an image with transparency.

    This node is useful for removing backgrounds or specific colors from images,
    commonly used for chroma keying (green screen removal) or similar effects.

    Parameters:
        input_image: The image to process
        color: The color to make transparent (hex format, e.g., #00ff00)
        tolerance: How much color variance to allow (0-255), higher values match more colors
        output: The resulting PNG image with transparency
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Input image
        self.add_parameter(
            ParameterImage(
                name="input_image",
                default_value=None,
                tooltip="The image to process",
                hide_property=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        # Color picker parameter
        self.add_parameter(
            Parameter(
                name="color",
                default_value="#00ff00",
                type="str",
                tooltip="Color to replace with transparency (hex format, e.g., #00ff00 for green)",
                traits={ColorPicker(format="hex")},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Tolerance parameter
        self.add_parameter(
            ParameterInt(
                name="tolerance",
                default_value=10,
                tooltip="How much color variance to allow (0-255). Higher values match more similar colors.",
                min_val=0,
                max_val=255,
                slider=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Output image
        self.add_parameter(
            ParameterImage(
                name="output",
                tooltip="The resulting image with the specified color made transparent",
                ui_options={"expander": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        """Process the image and replace the specified color with transparency."""
        input_image = self.get_parameter_value("input_image")

        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        self._process_image(input_image)

    def _process_image(self, image_artifact: ImageUrlArtifact) -> None:
        """Process the image and replace the target color with transparency."""
        try:
            # Load image
            image_pil = load_pil_from_url(image_artifact.value)

            # Get parameters
            color_hex = self.get_parameter_value("color") or "#00ff00"
            tolerance = self.get_parameter_value("tolerance")
            if tolerance is None:
                tolerance = 10

            # Parse the hex color to RGB
            target_rgb = parse_hex_color(color_hex)

            # Convert image to RGBA
            if image_pil.mode != "RGBA":
                image_pil = image_pil.convert("RGBA")

            # Convert to numpy array for efficient processing
            img_array = np.array(image_pil, dtype=np.float32)

            # Extract RGB channels (ignore alpha for color matching)
            rgb_array = img_array[:, :, :3]

            # Calculate color distance from target color
            target_array = np.array(target_rgb, dtype=np.float32)
            color_diff = np.abs(rgb_array - target_array)

            # Check if each pixel is within tolerance for all channels
            within_tolerance = np.all(color_diff <= tolerance, axis=2)

            # Create new alpha channel: 0 where color matches, preserve original elsewhere
            new_alpha = img_array[:, :, 3].copy()
            new_alpha[within_tolerance] = 0

            # Update alpha channel
            img_array[:, :, 3] = new_alpha

            # Convert back to PIL Image
            result_image = Image.fromarray(img_array.astype(np.uint8), mode="RGBA")

            # Save output image as PNG with proper filename
            filename = generate_filename(
                node_name=self.name,
                suffix="_transparent",
                extension="png",
            )
            output_artifact = save_pil_image_with_named_filename(result_image, filename, "PNG")
            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            error_msg = f"Failed to process image: {e!s}"
            logger.error(f"{self.name}: {error_msg}")
