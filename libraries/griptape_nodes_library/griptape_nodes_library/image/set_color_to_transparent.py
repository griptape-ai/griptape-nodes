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
    apply_mask_transformations,
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
        grow_shrink: Grow (negative) or shrink (positive) the transparent area
        blur_edges: Blur the edges of the transparent area for smoother transitions
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

        # Grow/shrink parameter for expanding or contracting the transparent area
        self.add_parameter(
            ParameterInt(
                name="grow_shrink",
                default_value=0,
                tooltip="Grow (negative) or shrink (positive) the transparent area. Useful for refining edges.",
                min_val=-100,
                max_val=100,
                slider=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Blur parameter for softening the edges of the transparent area
        self.add_parameter(
            ParameterInt(
                name="blur_edges",
                default_value=0,
                tooltip="Blur the edges of the transparent area for smoother transitions.",
                min_val=0,
                max_val=100,
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
            grow_shrink = self.get_parameter_value("grow_shrink") or 0
            blur_edges = self.get_parameter_value("blur_edges") or 0

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

            # Create a mask where matching pixels are black (0) and non-matching are white (255)
            # This represents the alpha channel: 0 = transparent, 255 = opaque
            mask_array = np.where(within_tolerance, 0, 255).astype(np.uint8)
            mask_pil = Image.fromarray(mask_array, mode="L")

            # Apply grow/shrink and blur transformations to the mask
            if grow_shrink != 0 or blur_edges != 0:
                mask_pil = apply_mask_transformations(
                    mask_pil,
                    grow_shrink=grow_shrink,
                    invert=False,
                    blur_radius=blur_edges,
                    context_name=self.name,
                )

            # Convert mask back to numpy array
            transformed_mask = np.array(mask_pil, dtype=np.float32)

            # Combine with original alpha: take minimum of original alpha and transformed mask
            # This preserves any existing transparency while adding new transparent areas
            original_alpha = img_array[:, :, 3]
            new_alpha = np.minimum(original_alpha, transformed_mask)

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
