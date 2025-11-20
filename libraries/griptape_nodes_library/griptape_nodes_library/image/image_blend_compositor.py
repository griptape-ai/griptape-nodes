from typing import Any, ClassVar

from PIL import Image, ImageChops

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class ImageBlendCompositor(BaseImageProcessor):
    """Compose two images using various blend modes with positioning and advanced compositing options."""

    # Blend mode options
    BLEND_MODE_OPTIONS: ClassVar[list[str]] = [
        "normal",
        "multiply",
        "screen",
        "overlay",
        "soft_light",
        "hard_light",
        "darken",
        "lighten",
        "difference",
        "exclusion",
        "add",
        "subtract",
        "logical_and",
        "logical_or",
        "logical_xor",
    ]

    # Opacity constants
    MIN_OPACITY = 0.0
    MAX_OPACITY = 1.0
    DEFAULT_OPACITY = 1.0

    # Position constants
    DEFAULT_POSITION = 0

    def _setup_custom_parameters(self) -> None:
        """Setup blend compositor parameters."""
        # Input parameters
        with ParameterGroup(name="inputs", ui_options={"collapsed": False}) as inputs_group:
            blend_image_param = Parameter(
                name="blend_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                tooltip="The image to blend/composite onto the base image",
            )
            self.add_parameter(blend_image_param)

        self.add_node_element(inputs_group)

        # Blend settings
        with ParameterGroup(name="blend_settings", ui_options={"collapsed": False}) as blend_group:
            # Blend mode
            blend_mode_param = Parameter(
                name="blend_mode",
                type="string",
                default_value="normal",
                tooltip="The blend mode to use for compositing",
            )
            blend_mode_param.add_trait(Options(choices=self.BLEND_MODE_OPTIONS))
            self.add_parameter(blend_mode_param)

            # Opacity
            opacity_param = Parameter(
                name="opacity",
                type="float",
                default_value=self.DEFAULT_OPACITY,
                tooltip=f"Opacity of the blend image ({self.MIN_OPACITY}-{self.MAX_OPACITY}, 0.0 = transparent, 1.0 = fully opaque)",
            )
            opacity_param.add_trait(Slider(min_val=self.MIN_OPACITY, max_val=self.MAX_OPACITY))
            self.add_parameter(opacity_param)

        self.add_node_element(blend_group)

        # Position and sizing
        with ParameterGroup(name="position_and_sizing", ui_options={"collapsed": False}) as position_group:
            # Blend position X
            blend_position_x_param = Parameter(
                name="blend_position_x",
                type="int",
                default_value=self.DEFAULT_POSITION,
                tooltip="X-coordinate position of the blend image (0 = center, negative = left, positive = right)",
            )
            self.add_parameter(blend_position_x_param)

            # Blend position Y
            blend_position_y_param = Parameter(
                name="blend_position_y",
                type="int",
                default_value=self.DEFAULT_POSITION,
                tooltip="Y-coordinate position of the blend image (0 = center, negative = up, positive = down)",
            )
            self.add_parameter(blend_position_y_param)

            # Resize blend to fit
            resize_blend_to_fit_param = Parameter(
                name="resize_blend_to_fit",
                type="bool",
                default_value=False,
                tooltip="Whether to resize the blend image to match the base image dimensions",
            )
            self.add_parameter(resize_blend_to_fit_param)

        self.add_node_element(position_group)

        # Advanced options
        with ParameterGroup(name="advanced_options", ui_options={"collapsed": True}) as advanced_group:
            # Preserve alpha
            preserve_alpha_param = Parameter(
                name="preserve_alpha",
                type="bool",
                default_value=True,
                tooltip="Whether to preserve the alpha channel of the blend image",
            )
            self.add_parameter(preserve_alpha_param)

            # Invert blend
            invert_blend_param = Parameter(
                name="invert_blend",
                type="bool",
                default_value=False,
                tooltip="Whether to invert the blend image before compositing",
            )
            self.add_parameter(invert_blend_param)

        self.add_node_element(advanced_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when inputs or parameters change."""
        if parameter.name in ["input_image", "blend_image"] and value is not None:
            # Check if both images are available
            image = self.get_parameter_value("input_image")
            blend_image = self.get_parameter_value("blend_image")
            if image is not None and blend_image is not None:
                self._process_images_immediately(image, blend_image)
        elif parameter.name in [
            "blend_mode",
            "opacity",
            "blend_position_x",
            "blend_position_y",
            "resize_blend_to_fit",
            "preserve_alpha",
            "invert_blend",
        ]:
            # Process when blend parameters change (for live preview)
            image = self.get_parameter_value("input_image")
            blend_image = self.get_parameter_value("blend_image")
            if image is not None and blend_image is not None:
                self._process_images_immediately(image, blend_image)
        return super().after_value_set(parameter, value)

    def _process_images_immediately(self, image_value: Any, blend_image_value: Any) -> None:
        """Process images immediately for live preview."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                image_artifact = dict_to_image_url_artifact(image_value)
            else:
                image_artifact = image_value

            if isinstance(blend_image_value, dict):
                blend_image_artifact = dict_to_image_url_artifact(blend_image_value)
            else:
                blend_image_artifact = blend_image_value

            # Load PIL images
            image_pil = load_pil_from_url(image_artifact.value)
            blend_pil = load_pil_from_url(blend_image_artifact.value)

            # Process with current settings
            processed_image = self._process_images(image_pil, blend_pil, **self._get_custom_parameters())

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
        return "image blend compositing"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:  # noqa: ARG002
        """Process a single image (required by BaseImageProcessor)."""
        # This method is required by the abstract base class but not used for this node
        # since we work with two images. Return the input image unchanged.
        return pil_image

    def _process_images(self, image_pil: Image.Image, blend_pil: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL images by compositing them together."""
        blend_mode = kwargs.get("blend_mode", "normal")
        opacity = kwargs.get("opacity", self.DEFAULT_OPACITY)
        blend_position_x = kwargs.get("blend_position_x", self.DEFAULT_POSITION)
        blend_position_y = kwargs.get("blend_position_y", self.DEFAULT_POSITION)
        resize_blend_to_fit = kwargs.get("resize_blend_to_fit", False)
        preserve_alpha = kwargs.get("preserve_alpha", True)
        invert_blend = kwargs.get("invert_blend", False)

        # Convert images to RGBA for alpha channel support
        if image_pil.mode != "RGBA":
            image_pil = image_pil.convert("RGBA")
        if blend_pil.mode != "RGBA":
            blend_pil = blend_pil.convert("RGBA")

        # Invert blend image if requested (preserve alpha channel)
        if invert_blend:
            # Extract alpha channel before inverting
            alpha_channel = blend_pil.getchannel("A") if blend_pil.mode == "RGBA" else None

            # Invert only the RGB channels
            rgb_channels = blend_pil.convert("RGB")
            inverted_rgb = ImageChops.invert(rgb_channels)

            # Reconstruct the image with original alpha
            if alpha_channel is not None:
                blend_pil = Image.merge("RGBA", (*inverted_rgb.split(), alpha_channel))
            else:
                blend_pil = inverted_rgb.convert("RGBA")

        # Resize blend image if requested
        if resize_blend_to_fit:
            blend_pil = blend_pil.resize(image_pil.size, Image.Resampling.LANCZOS)

        # Calculate position (center blend image by default)
        if blend_position_x == 0 and blend_position_y == 0:
            # Center the blend image
            x = (image_pil.width - blend_pil.width) // 2
            y = (image_pil.height - blend_pil.height) // 2
        else:
            # Use specified position
            x = blend_position_x
            y = blend_position_y

        # Create a new image with the base image
        result = image_pil.copy()

        # Apply blend mode
        if blend_mode == "normal":
            # Simple alpha compositing
            if opacity < 1.0:
                # Apply opacity to blend image
                blend_pil.putalpha(int(255 * opacity))
            blended_image = blend_pil
        else:
            # Apply custom blend mode
            blended_image = self._apply_blend_mode(image_pil, blend_pil, blend_mode, opacity)

        # Apply the blended image with proper alpha handling
        result = self._apply_blended_image(result, blended_image, (x, y), preserve_alpha=preserve_alpha)

        return result

    def _apply_blended_image(
        self,
        result: Image.Image,
        blended_image: Image.Image,
        position: tuple[int, int],
        *,
        preserve_alpha: bool,
    ) -> Image.Image:
        """Apply the blended image to the result with proper alpha handling."""
        if preserve_alpha:
            # Use the blended image's alpha channel as a mask for proper transparency
            if blended_image.mode == "RGBA":
                result.paste(blended_image, position, blended_image)
            else:
                result.paste(blended_image, position)
        else:
            # Paste without alpha (ignore transparency)
            result.paste(blended_image, position)
        return result

    def _apply_blend_mode(self, base: Image.Image, blend: Image.Image, mode: str, opacity: float) -> Image.Image:
        """Apply a specific blend mode to two images."""
        # Ensure both images are the same size for blending
        if base.size != blend.size:
            blend = blend.resize(base.size, Image.Resampling.LANCZOS)

        # Convert to RGB for mathematical operations (ImageChops works with RGB)
        base_rgb = base.convert("RGB")
        blend_rgb = blend.convert("RGB")

        # Apply the blend mode using a mapping approach
        result = self._get_blend_result(base_rgb, blend_rgb, mode)

        # Apply opacity by blending the result with the base image
        if opacity < 1.0:
            # Blend the result with the original base image at the specified opacity
            result = Image.blend(base_rgb, result, opacity)

        # Convert result back to RGBA to preserve alpha channel support
        result_rgba = result.convert("RGBA")

        # Apply the blend image's alpha channel to the result
        if blend.mode == "RGBA":
            blend_alpha = blend.getchannel("A")
            result_rgba.putalpha(blend_alpha)
        else:
            # If blend image has no alpha, create a fully opaque alpha channel
            result_rgba.putalpha(255)

        return result_rgba

    def _get_blend_result(self, base_rgb: Image.Image, blend_rgb: Image.Image, mode: str) -> Image.Image:
        """Get the result of applying a specific blend mode."""
        # Map blend modes to their corresponding ImageChops functions
        blend_functions = {
            "multiply": lambda: self._custom_multiply(base_rgb, blend_rgb),
            "screen": lambda: ImageChops.screen(base_rgb, blend_rgb),
            "overlay": lambda: ImageChops.overlay(base_rgb, blend_rgb),
            "soft_light": lambda: ImageChops.soft_light(base_rgb, blend_rgb),
            "hard_light": lambda: ImageChops.hard_light(base_rgb, blend_rgb),
            "darken": lambda: ImageChops.darker(base_rgb, blend_rgb),
            "lighten": lambda: ImageChops.lighter(base_rgb, blend_rgb),
            "difference": lambda: ImageChops.difference(base_rgb, blend_rgb),
            "exclusion": lambda: ImageChops.logical_xor(base_rgb, blend_rgb),
            "add": lambda: ImageChops.add(base_rgb, blend_rgb),
            "subtract": lambda: ImageChops.subtract(base_rgb, blend_rgb),
            "logicaland": lambda: ImageChops.logical_and(base_rgb, blend_rgb),
            "logical_or": lambda: ImageChops.logical_or(base_rgb, blend_rgb),
            "logical_xor": lambda: ImageChops.logical_xor(base_rgb, blend_rgb),
        }

        # Get the blend function or default to normal blending
        blend_func = blend_functions.get(mode, lambda: blend_rgb)
        return blend_func()

    def _custom_multiply(self, base: Image.Image, blend: Image.Image) -> Image.Image:
        """Custom multiply implementation to ensure correct math."""
        # Convert images to numpy arrays for pixel-level operations
        import numpy as np

        # Convert PIL images to numpy arrays (0-255 range)
        base_array = np.array(base, dtype=np.float32)
        blend_array = np.array(blend, dtype=np.float32)

        # Normalize to 0-1 range for proper multiply math
        base_norm = base_array / 255.0
        blend_norm = blend_array / 255.0

        # Apply multiply: result = base * blend
        result_norm = base_norm * blend_norm

        # Convert back to 0-255 range and ensure proper data type
        result_array = np.clip(result_norm * 255.0, 0, 255).astype(np.uint8)

        # Convert back to PIL image
        return Image.fromarray(result_array)

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate blend compositor parameters."""
        exceptions = []

        # Check that both images are provided
        input_image = self.get_parameter_value("input_image")
        blend_image = self.get_parameter_value("blend_image")
        if input_image is None:
            exceptions.append(ValueError(f"{self.name} - Input image is required"))
        if blend_image is None:
            exceptions.append(ValueError(f"{self.name} - Blend image is required"))

        # Validate opacity
        opacity = self.get_parameter_value("opacity")
        if opacity is not None and (opacity < self.MIN_OPACITY or opacity > self.MAX_OPACITY):
            msg = f"{self.name} - Opacity must be between {self.MIN_OPACITY} and {self.MAX_OPACITY}, got {opacity}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get blend compositor parameters."""
        return {
            "blend_mode": self.get_parameter_value("blend_mode"),
            "opacity": self.get_parameter_value("opacity"),
            "blend_position_x": self.get_parameter_value("blend_position_x"),
            "blend_position_y": self.get_parameter_value("blend_position_y"),
            "resize_blend_to_fit": self.get_parameter_value("resize_blend_to_fit"),
            "preserve_alpha": self.get_parameter_value("preserve_alpha"),
            "invert_blend": self.get_parameter_value("invert_blend"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_blend"

    async def aprocess(self) -> None:
        """Main workflow execution method."""
        # Reset execution state and clear status
        self._clear_execution_status()

        # Get input images
        base_image = self.get_parameter_value("input_image")
        blend_image = self.get_parameter_value("blend_image")

        if base_image is None or blend_image is None:
            return

        # Process the images directly for workflow execution
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(base_image, dict):
                base_image = dict_to_image_url_artifact(base_image)

            if isinstance(blend_image, dict):
                blend_image = dict_to_image_url_artifact(blend_image)

            # Load PIL images
            image_pil = load_pil_from_url(base_image.value)
            blend_pil = load_pil_from_url(blend_image.value)

            # Process with current settings
            processed_image = self._process_images(image_pil, blend_pil, **self._get_custom_parameters())

            # Save and set output with proper filename
            # Generate a meaningful filename with processing parameters
            filename = self._generate_processed_image_filename("png")
            output_artifact = save_pil_image_with_named_filename(processed_image, filename, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

            # Set success status with detailed information
            success_details = (
                f"Successfully composed images: {self._get_processing_description()}\n"
                f"Base: {image_pil.width}x{image_pil.height}\n"
                f"Blend: {blend_pil.width}x{blend_pil.height}\n"
                f"Output: {processed_image.width}x{processed_image.height}"
            )
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"{self.name}: Processing failed: {error_message}")

            # Set failure status with detailed error information
            failure_details = f"Image composition failed: {self._get_processing_description()}\nError: {error_message}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {failure_details}")

            # Handle failure based on whether failure output is connected
            self._handle_failure_exception(ValueError(error_message))
            raise
