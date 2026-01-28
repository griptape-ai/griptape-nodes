import asyncio
from typing import Any

import numpy as np
from griptape.artifacts import ImageUrlArtifact
from PIL import Image, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_to_static_file,
)


class GaussianEdgeFade(DataNode):
    """Apply Gaussian blur fade to image edges for smooth compositing."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Image"
        self.description = "Apply Gaussian blur fade to image edges for smooth compositing"

        # Input image parameter
        self.add_parameter(
            ParameterImage(
                name="input_image",
                default_value=None,
                tooltip="The input image to apply edge fade to",
                hide_property=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        # Fade mode parameter
        self.add_parameter(
            ParameterString(
                name="fade_mode",
                tooltip="How to measure the fade distance: percentage of image size or absolute pixels",
                default_value="percentage",
                traits={Options(choices=["percentage", "pixels"])},
            )
        )

        # Fade distance parameter
        self.add_parameter(
            ParameterInt(
                name="fade_distance",
                tooltip="Distance from edge to fade (5 = 5% of image dimension in percentage mode, or 5 pixels in pixel mode)",
                default_value=5,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Slider(min_val=0, max_val=50)},
            )
        )

        # Blur radius parameter
        self.add_parameter(
            ParameterInt(
                name="blur_radius",
                tooltip="Gaussian blur radius for smooth edge transition (higher = softer fade)",
                default_value=10,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                traits={Slider(min_val=0, max_val=100)},
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="fade_curve",
                tooltip="Fade curve shape: 1.0=linear, >1.0=more transparent near edges (aggressive fade), <1.0=less transparent near edges (gentle fade)",
                default_value=2.0,
                traits={Slider(min_val=0.5, max_val=4.0)},
            )
        )

        self.add_parameter(
            ParameterString(
                name="edge_shape",
                tooltip="Shape of the fade: square (straight edges) or rounded (curved corners)",
                default_value="square",
                traits={Options(choices=["square", "rounded"])},
            )
        )

        self.add_parameter(
            ParameterBool(
                name="replace_mask",
                tooltip="If False, combines edge fade with existing alpha channel. If True, replaces existing alpha entirely.",
                default_value=False,
            )
        )

        # Edge selection parameters (individual booleans for each edge)
        self.add_parameter(
            ParameterBool(
                name="apply_top",
                tooltip="Apply fade to top edge",
                default_value=True,
            )
        )

        self.add_parameter(
            ParameterBool(
                name="apply_bottom",
                tooltip="Apply fade to bottom edge",
                default_value=True,
            )
        )

        self.add_parameter(
            ParameterBool(
                name="apply_left",
                tooltip="Apply fade to left edge",
                default_value=True,
            )
        )

        self.add_parameter(
            ParameterBool(
                name="apply_right",
                tooltip="Apply fade to right edge",
                default_value=True,
            )
        )

        # Output image parameter
        self.add_parameter(
            ParameterImage(
                name="output_image",
                tooltip="The processed image with alpha channel edge fade",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update UI when fade_mode changes."""
        if parameter.name == "fade_mode":
            fade_distance_param = self.get_parameter_by_name("fade_distance")
            if fade_distance_param:
                if value == "percentage":
                    fade_distance_param.tooltip = (
                        "Distance from edge to fade as percentage of image dimension (e.g., 5 = 5%)"
                    )
                else:  # pixels
                    fade_distance_param.tooltip = "Distance from edge to fade in pixels (e.g., 50 = 50 pixels)"

        return super().after_value_set(parameter, value)

    def process(self) -> AsyncResult[None]:
        """Non-blocking entry point for Griptape engine."""
        yield lambda: self._process_sync()

    def _process_sync(self) -> None:
        """Synchronous wrapper that runs async code."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process_async())
        finally:
            loop.close()

    async def _process_async(self) -> None:
        """Process the image to apply edge fade."""
        input_image = self.get_parameter_value("input_image")
        if input_image is None:
            return

        # Normalize input to ImageUrlArtifact
        if isinstance(input_image, dict):
            input_image = dict_to_image_url_artifact(input_image)

        # Get all parameters
        fade_mode = self.get_parameter_value("fade_mode")
        fade_distance = self.get_parameter_value("fade_distance")
        blur_radius = self.get_parameter_value("blur_radius")
        fade_curve = self.get_parameter_value("fade_curve")
        edge_shape = self.get_parameter_value("edge_shape")
        replace_mask = self.get_parameter_value("replace_mask")

        apply_edges = {
            "top": self.get_parameter_value("apply_top"),
            "bottom": self.get_parameter_value("apply_bottom"),
            "left": self.get_parameter_value("apply_left"),
            "right": self.get_parameter_value("apply_right"),
        }

        # Process the image
        result_image = self._apply_edge_fade(
            input_image, fade_mode, fade_distance, blur_radius, fade_curve, edge_shape, replace_mask, apply_edges
        )

        # Set output
        self.set_parameter_value("output_image", result_image)
        self.publish_update_to_parameter("output_image", result_image)

    def _apply_edge_fade(  # noqa: PLR0912, PLR0913, C901
        self,
        image_artifact: ImageUrlArtifact,
        fade_mode: str,
        fade_distance: int,
        blur_radius: int,
        fade_curve: float,
        edge_shape: str,
        replace_mask: bool,  # noqa: FBT001
        apply_edges: dict[str, bool],
    ) -> ImageUrlArtifact:
        """Apply Gaussian-blurred alpha fade to specified edges."""
        # Load original image
        original_image = load_pil_from_url(image_artifact.value)

        # Store original alpha channel if preserving it
        original_alpha = None
        if not replace_mask and original_image.mode == "RGBA":
            original_alpha = original_image.getchannel("A")

        # Convert to RGBA to support alpha channel
        if original_image.mode != "RGBA":
            original_image = original_image.convert("RGBA")

        width, height = original_image.size

        # Create alpha mask (initially fully opaque - white)
        alpha_mask = Image.new("L", (width, height), 255)

        # Calculate fade distance in pixels
        if fade_mode == "percentage":
            # Use the smaller dimension to calculate percentage
            reference_dim = min(width, height)
            fade_pixels = int(reference_dim * fade_distance / 100.0)
        else:  # pixels
            fade_pixels = int(fade_distance)

        # Clamp fade_pixels to reasonable values
        max_fade_width = width // 2
        max_fade_height = height // 2
        fade_pixels = max(0, fade_pixels)

        # Create gradients for each edge if selected
        if fade_pixels > 0:
            # Convert to numpy array for easier manipulation
            mask_array = np.array(alpha_mask, dtype=np.float32)

            if edge_shape == "square":
                # Square edges - independent fade for each edge
                if apply_edges["top"] and fade_pixels <= max_fade_height:
                    # Top edge: gradient from 0 (transparent) at y=0 to 255 (opaque) at y=fade_pixels
                    # Use power curve for more control over fade shape
                    for y in range(min(fade_pixels, height)):
                        normalized_distance = y / fade_pixels
                        alpha_value = int(255 * (normalized_distance**fade_curve))
                        mask_array[y, :] = np.minimum(mask_array[y, :], alpha_value)

                if apply_edges["bottom"] and fade_pixels <= max_fade_height:
                    # Bottom edge: gradient from 255 (opaque) at y=height-fade_pixels to 0 (transparent) at y=height
                    for y in range(max(0, height - fade_pixels), height):
                        distance_from_bottom = height - y
                        normalized_distance = distance_from_bottom / fade_pixels
                        alpha_value = int(255 * (normalized_distance**fade_curve))
                        mask_array[y, :] = np.minimum(mask_array[y, :], alpha_value)

                if apply_edges["left"] and fade_pixels <= max_fade_width:
                    # Left edge: gradient from 0 (transparent) at x=0 to 255 (opaque) at x=fade_pixels
                    for x in range(min(fade_pixels, width)):
                        normalized_distance = x / fade_pixels
                        alpha_value = int(255 * (normalized_distance**fade_curve))
                        mask_array[:, x] = np.minimum(mask_array[:, x], alpha_value)

                if apply_edges["right"] and fade_pixels <= max_fade_width:
                    # Right edge: gradient from 255 (opaque) at x=width-fade_pixels to 0 (transparent) at x=width
                    for x in range(max(0, width - fade_pixels), width):
                        distance_from_right = width - x
                        normalized_distance = distance_from_right / fade_pixels
                        alpha_value = int(255 * (normalized_distance**fade_curve))
                        mask_array[:, x] = np.minimum(mask_array[:, x], alpha_value)

            else:  # rounded
                # Rounded edges - calculate distance from rounded rectangle
                mask_array = self._create_rounded_mask(width, height, fade_pixels, fade_curve, apply_edges)

            # Convert back to PIL Image
            alpha_mask = Image.fromarray(mask_array.astype(np.uint8), mode="L")

        # Apply Gaussian blur to the mask for smooth transitions
        if blur_radius > 0:
            alpha_mask = alpha_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Combine with original alpha channel if preserve mode
        if not replace_mask and original_alpha is not None:
            # Convert both to numpy arrays for multiplication
            original_alpha_array = np.array(original_alpha, dtype=np.float32)
            new_alpha_array = np.array(alpha_mask, dtype=np.float32)

            # Multiply the alpha channels (normalized to 0-1 range)
            combined_alpha_array = (original_alpha_array / 255.0) * (new_alpha_array / 255.0) * 255.0

            # Convert back to PIL Image
            alpha_mask = Image.fromarray(combined_alpha_array.astype(np.uint8), mode="L")

        # Apply the alpha mask to the original image
        original_image.putalpha(alpha_mask)

        # Save and return result
        result_artifact = save_pil_image_to_static_file(original_image)
        return result_artifact

    def _create_rounded_mask(  # noqa: PLR0912, PLR0915, C901
        self, width: int, height: int, fade_pixels: int, fade_curve: float, apply_edges: dict[str, bool]
    ) -> np.ndarray:
        """Create a rounded rectangle mask with smooth corner transitions."""
        # Calculate fade margins for each edge
        fade_top = fade_pixels if apply_edges["top"] else 0
        fade_bottom = fade_pixels if apply_edges["bottom"] else 0
        fade_left = fade_pixels if apply_edges["left"] else 0
        fade_right = fade_pixels if apply_edges["right"] else 0

        # For rounded corners, we need to calculate the minimum distance to the "safe zone"
        # The safe zone is the inner rectangle that's fully opaque
        safe_top = fade_top
        safe_bottom = height - fade_bottom
        safe_left = fade_left
        safe_right = width - fade_right

        # Initialize distance field (positive = inside fade zone, negative = outside)
        distance_field = np.zeros((height, width), dtype=np.float32)

        for y in range(height):
            for x in range(width):
                # Calculate distances to safe zone boundaries
                dx_left = x - safe_left if x < safe_left else 0
                dx_right = x - (safe_right - 1) if x >= safe_right else 0
                dy_top = y - safe_top if y < safe_top else 0
                dy_bottom = y - (safe_bottom - 1) if y >= safe_bottom else 0

                # Determine which region we're in
                in_left = x < safe_left
                in_right = x >= safe_right
                in_top = y < safe_top
                in_bottom = y >= safe_bottom

                if in_top and in_left:
                    # Top-left corner region
                    distance_field[y, x] = np.sqrt(dx_left**2 + dy_top**2)
                elif in_top and in_right:
                    # Top-right corner region
                    distance_field[y, x] = np.sqrt(dx_right**2 + dy_top**2)
                elif in_bottom and in_left:
                    # Bottom-left corner region
                    distance_field[y, x] = np.sqrt(dx_left**2 + dy_bottom**2)
                elif in_bottom and in_right:
                    # Bottom-right corner region
                    distance_field[y, x] = np.sqrt(dx_right**2 + dy_bottom**2)
                elif in_top:
                    # Top edge (no corner)
                    distance_field[y, x] = abs(dy_top)
                elif in_bottom:
                    # Bottom edge (no corner)
                    distance_field[y, x] = abs(dy_bottom)
                elif in_left:
                    # Left edge (no corner)
                    distance_field[y, x] = abs(dx_left)
                elif in_right:
                    # Right edge (no corner)
                    distance_field[y, x] = abs(dx_right)
                else:
                    # Inside safe zone - fully opaque
                    distance_field[y, x] = 0

        # Convert distances to alpha values using fade curve
        mask_array = np.zeros((height, width), dtype=np.float32)

        for y in range(height):
            for x in range(width):
                dist = distance_field[y, x]

                if dist <= 0:
                    # Inside safe zone
                    mask_array[y, x] = 255
                else:
                    # In fade zone - determine which fade distance to use
                    in_left = x < safe_left
                    in_right = x >= safe_right
                    in_top = y < safe_top
                    in_bottom = y >= safe_bottom

                    # Get the maximum fade distance that applies to this pixel
                    max_fade = fade_pixels

                    if dist >= max_fade:
                        mask_array[y, x] = 0
                    else:
                        normalized_distance = 1.0 - (dist / max_fade)
                        mask_array[y, x] = 255 * (normalized_distance**fade_curve)

        return mask_array
