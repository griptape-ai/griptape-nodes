from typing import Any

from PIL import Image, ImageChops

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class ImageBlendCompositor(BaseImageProcessor):
    """Compose two images using various blend modes with positioning and advanced compositing options."""

    # Blend mode options
    BLEND_MODE_OPTIONS = [
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
    MIN_POSITION = -1000
    MAX_POSITION = 1000
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
                tooltip=f"X-coordinate position of the blend image ({self.MIN_POSITION}-{self.MAX_POSITION}, 0 = center, negative = left, positive = right)",
            )
            self.add_parameter(blend_position_x_param)

            # Blend position Y
            blend_position_y_param = Parameter(
                name="blend_position_y",
                type="int",
                default_value=self.DEFAULT_POSITION,
                tooltip=f"Y-coordinate position of the blend image ({self.MIN_POSITION}-{self.MAX_POSITION}, 0 = center, negative = up, positive = down)",
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

        """Process images immediately with a parameter override to avoid timing issues."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

                image_artifact = dict_to_image_url_artifact(image_value)
            else:
                image_artifact = image_value

            if isinstance(blend_image_value, dict):
                from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

                blend_image_artifact = dict_to_image_url_artifact(blend_image_value)
            else:
                blend_image_artifact = blend_image_value

            # Load PIL images
            from griptape_nodes_library.utils.image_utils import load_pil_from_url

            image_pil = load_pil_from_url(image_artifact.value)
            blend_pil = load_pil_from_url(blend_image_artifact.value)

            # Get current parameters but override the one that just changed
            params = self._get_custom_parameters()
            params[param_name] = param_value

            # Process with current settings (including the override)
            processed_image = self._process_images(image_pil, blend_pil, **params)

            # Save and set output
            from griptape_nodes_library.utils.image_utils import save_pil_image_to_static_file

            output_artifact = save_pil_image_to_static_file(processed_image, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            # Log error but don't fail the node
            from griptape_nodes.retained_mode.griptape_nodes import logger

            logger.warning(f"{self.name}: Live preview failed: {e}")

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "image blend compositing"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
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

        # Invert blend image if requested
        if invert_blend:
            blend_pil = ImageChops.invert(blend_pil)

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
            result.paste(blend_pil, (x, y), blend_pil if preserve_alpha else None)
        else:
            # Apply custom blend mode
            blended = self._apply_blend_mode(image_pil, blend_pil, blend_mode, opacity)
            result.paste(blended, (x, y), blended if preserve_alpha else None)

        return result

    def _apply_blend_mode(self, base: Image.Image, blend: Image.Image, mode: str, opacity: float) -> Image.Image:
        """Apply a specific blend mode to two images."""
        # Ensure both images are the same size for blending
        if base.size != blend.size:
            blend = blend.resize(base.size, Image.Resampling.LANCZOS)

        # Convert to RGB for mathematical operations (ImageChops works with RGB)
        base_rgb = base.convert("RGB")
        blend_rgb = blend.convert("RGB")

        # Apply the blend mode first
        if mode == "multiply":
            # Custom multiply implementation to ensure correct math
            result = self._custom_multiply(base_rgb, blend_rgb)
        elif mode == "screen":
            result = ImageChops.screen(base_rgb, blend_rgb)
        elif mode == "overlay":
            result = ImageChops.overlay(base_rgb, blend_rgb)
        elif mode == "soft_light":
            result = ImageChops.soft_light(base_rgb, blend_rgb)
        elif mode == "hard_light":
            result = ImageChops.hard_light(base_rgb, blend_rgb)
        elif mode == "darken":
            result = ImageChops.darker(base_rgb, blend_rgb)
        elif mode == "lighten":
            result = ImageChops.lighter(base_rgb, blend_rgb)
        elif mode == "difference":
            result = ImageChops.difference(base_rgb, blend_rgb)
        elif mode == "exclusion":
            result = ImageChops.logical_xor(base_rgb, blend_rgb)
        elif mode == "add":
            result = ImageChops.add(base_rgb, blend_rgb)
        elif mode == "subtract":
            result = ImageChops.subtract(base_rgb, blend_rgb)
        elif mode == "logicaland":
            result = ImageChops.logical_and(base_rgb, blend_rgb)
        elif mode == "logical_or":
            result = ImageChops.logical_or(base_rgb, blend_rgb)
        elif mode == "logical_xor":
            result = ImageChops.logical_xor(base_rgb, blend_rgb)
        else:
            # Default to normal blending
            result = blend_rgb

        # Apply opacity by blending the result with the base image
        if opacity < 1.0:
            # Blend the result with the original base image at the specified opacity
            result = Image.blend(base_rgb, result, opacity)

        return result

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

    # def _validate_custom_parameters(self) -> list[Exception] | None:
    #     """Validate blend compositor parameters."""
    #     exceptions = []

    #     # Check that both images are provided
    #     base_image = self.get_parameter_value("input_image")
    #     blend_image = self.get_parameter_value("blend_image")
    #     if base_image is None:
    #         exceptions.append(ValueError(f"{self.name} - Input image is required"))
    #     if blend_image is None:
    #         exceptions.append(ValueError(f"{self.name} - Blend image is required"))

    #     # Validate opacity
    #     opacity = self.get_parameter_value("opacity")
    #     if opacity is not None and (opacity < self.MIN_OPACITY or opacity > self.MAX_OPACITY):
    #         msg = f"{self.name} - Opacity must be between {self.MIN_OPACITY} and {self.MAX_OPACITY}, got {opacity}"
    #         exceptions.append(ValueError(msg))

    #     # Validate position
    #     blend_position_x = self.get_parameter_value("blend_position_x")
    #     if blend_position_x is not None and (
    #         blend_position_x < self.MIN_POSITION or blend_position_x > self.MAX_POSITION
    #     ):
    #         msg = f"{self.name} - Blend position X must be between {self.MIN_POSITION} and {self.MAX_POSITION}, got {blend_position_x}"
    #         exceptions.append(ValueError(msg))

    #     blend_position_y = self.get_parameter_value("blend_position_y")
    #     if blend_position_y is not None and (
    #         blend_position_y < self.MIN_POSITION or blend_position_y > self.MAX_POSITION
    #     ):
    #         msg = f"{self.name} - Blend position Y must be between {self.MIN_POSITION} and {self.MAX_POSITION}, got {blend_position_y}"
    #         exceptions.append(ValueError(msg))

    #     return exceptions if exceptions else None

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

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        blend_mode = kwargs.get("blend_mode", "normal")
        opacity = kwargs.get("opacity", self.DEFAULT_OPACITY)
        return f"_blend_{blend_mode}_op{opacity:.2f}"

    def process(self) -> None:
        """Main workflow execution method."""
        # Get input images
        base_image = self.get_parameter_value("input_image")
        blend_image = self.get_parameter_value("blend_image")

        if base_image is None or blend_image is None:
            return

        # Process the images directly for workflow execution
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(base_image, dict):
                from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

                base_image = dict_to_image_url_artifact(base_image)

            if isinstance(blend_image, dict):
                from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

                blend_image = dict_to_image_url_artifact(blend_image)

            # Load PIL images
            from griptape_nodes_library.utils.image_utils import load_pil_from_url

            image_pil = load_pil_from_url(base_image.value)
            blend_pil = load_pil_from_url(blend_image.value)

            # Process with current settings
            processed_image = self._process_images(image_pil, blend_pil, **self._get_custom_parameters())

            # Save and set output
            from griptape_nodes_library.utils.image_utils import save_pil_image_to_static_file

            output_artifact = save_pil_image_to_static_file(processed_image, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

        except Exception as e:
            from griptape_nodes.retained_mode.griptape_nodes import logger

            logger.error(f"{self.name}: Processing failed: {e}")
            raise
