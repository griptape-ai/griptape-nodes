"""ColorMatch node for transferring color characteristics between images.

This node transfers color characteristics from a reference image to a target image
using the color-matcher library. It supports multiple color transfer algorithms
including Monge-Kantorovich Linearization, Histogram Matching, Reinhard et al.,
and Multi-Variate Gaussian Distribution methods.
"""

from typing import Any, ClassVar

import numpy as np
from PIL import Image

from color_matcher import ColorMatcher

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class ColorMatch(BaseImageProcessor):
    """Transfer color characteristics from a reference image to a target image.

    This node uses the color-matcher library to perform color transfer between images,
    which is useful for automatic color grading of photographs, paintings, and video
    sequences, as well as light-field and stop-motion corrections.

    Features:
    - Multiple color transfer algorithms (MKL, Histogram Matching, Reinhard, MVGD)
    - Adjustable transfer strength for blending
    - Live preview when parameters change
    """

    # Available color transfer methods
    COLOR_MATCH_METHODS: ClassVar[list[str]] = [
        "mkl",  # Monge-Kantorovich Linearization (fast, good quality)
        "hm",  # Histogram Matching
        "reinhard",  # Reinhard et al. color transfer
        "mvgd",  # Multi-Variate Gaussian Distribution
        "hm-mvgd-hm",  # Compound method (best quality)
        "hm-mkl-hm",  # Alternative compound method
    ]

    # Strength constants
    MIN_STRENGTH = 0.0
    MAX_STRENGTH = 10.0
    DEFAULT_STRENGTH = 1.0

    def _setup_custom_parameters(self) -> None:
        """Setup color match specific parameters."""
        # Reference image input
        with ParameterGroup(name="inputs", ui_options={"collapsed": False}) as inputs_group:
            ref_image_param = ParameterImage(
                name="reference_image",
                tooltip="Reference image - the source of the color palette to transfer",
            )
            self.add_parameter(ref_image_param)

        self.add_node_element(inputs_group)

        # Color match settings
        with ParameterGroup(name="color_match_settings", ui_options={"collapsed": False}) as settings_group:
            # Method selection
            method_param = ParameterString(
                name="method",
                default_value="mkl",
                tooltip=(
                    "Color transfer algorithm:\n"
                    "• mkl: Monge-Kantorovich Linearization (fast, default)\n"
                    "• hm: Histogram Matching\n"
                    "• reinhard: Reinhard et al. color transfer\n"
                    "• mvgd: Multi-Variate Gaussian Distribution\n"
                    "• hm-mvgd-hm: Compound method (best quality)\n"
                    "• hm-mkl-hm: Alternative compound method"
                ),
            )
            method_param.add_trait(Options(choices=self.COLOR_MATCH_METHODS))
            self.add_parameter(method_param)

            # Strength parameter
            strength_param = ParameterFloat(
                name="strength",
                default_value=self.DEFAULT_STRENGTH,
                tooltip=(
                    f"Blending strength ({self.MIN_STRENGTH}-{self.MAX_STRENGTH}):\n"
                    "0.0 = no change, 1.0 = full color transfer\n"
                    "Values > 1.0 exaggerate the effect"
                ),
            )
            strength_param.add_trait(Slider(min_val=self.MIN_STRENGTH, max_val=self.MAX_STRENGTH))
            self.add_parameter(strength_param)

        self.add_node_element(settings_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when inputs or parameters change."""
        if parameter.name in ["input_image", "reference_image"] and value is not None:
            # Check if both images are available
            target_image = self.get_parameter_value("input_image")
            ref_image = self.get_parameter_value("reference_image")
            if target_image is not None and ref_image is not None:
                self._process_images_immediately(target_image, ref_image)
        elif parameter.name in ["method", "strength"]:
            # Process when color match parameters change (for live preview)
            target_image = self.get_parameter_value("input_image")
            ref_image = self.get_parameter_value("reference_image")
            if target_image is not None and ref_image is not None:
                self._process_images_immediately(target_image, ref_image)
        return super().after_value_set(parameter, value)

    def _process_images_immediately(self, target_value: Any, ref_value: Any) -> None:
        """Process images immediately for live preview."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(target_value, dict):
                target_artifact = dict_to_image_url_artifact(target_value)
            else:
                target_artifact = target_value

            if isinstance(ref_value, dict):
                ref_artifact = dict_to_image_url_artifact(ref_value)
            else:
                ref_artifact = ref_value

            # Load PIL images
            target_pil = load_pil_from_url(target_artifact.value)
            ref_pil = load_pil_from_url(ref_artifact.value)

            # Process with current settings
            processed_image = self._process_images(target_pil, ref_pil, **self._get_custom_parameters())

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
        return "color matching/transfer"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:  # noqa: ARG002
        """Process a single image (required by BaseImageProcessor).

        This method is required by the abstract base class but not used for this node
        since we work with two images. Return the input image unchanged.
        """
        return pil_image

    def _process_images(self, target_pil: Image.Image, ref_pil: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL images by applying color transfer.

        Args:
            target_pil: The target image to apply color transfer to
            ref_pil: The reference image providing the color palette
            **kwargs: Additional parameters (method, strength)

        Returns:
            The color-matched image
        """
        method = kwargs.get("method", "mkl")
        strength = kwargs.get("strength", self.DEFAULT_STRENGTH)

        # Skip processing if strength is 0
        if strength == 0:
            logger.debug(f"{self.name}: Strength is 0, returning target image unchanged")
            return target_pil

        # Convert images to RGB if necessary
        if target_pil.mode != "RGB":
            target_pil = target_pil.convert("RGB")
        if ref_pil.mode != "RGB":
            ref_pil = ref_pil.convert("RGB")

        # Convert to float32 numpy arrays in 0-1 range (format expected by color-matcher)
        target_np = np.array(target_pil, dtype=np.float32) / 255.0
        ref_np = np.array(ref_pil, dtype=np.float32) / 255.0

        # Ensure C-contiguous arrays
        if not target_np.flags["C_CONTIGUOUS"]:
            target_np = np.ascontiguousarray(target_np)
        if not ref_np.flags["C_CONTIGUOUS"]:
            ref_np = np.ascontiguousarray(ref_np)

        logger.debug(
            f"{self.name}: Processing with method={method}, strength={strength}, "
            f"target={target_np.shape}, ref={ref_np.shape}"
        )

        # Apply color matching
        cm = ColorMatcher()
        result = cm.transfer(src=target_np, ref=ref_np, method=method)

        # Apply strength blending if not 1.0
        # Formula: result = target + strength * (result - target)
        if strength != 1.0:
            result = target_np + strength * (result - target_np)

        # Clamp values to valid range
        result = np.clip(result, 0, 1)

        # Convert back to PIL Image
        result_uint8 = (result * 255).astype(np.uint8)
        return Image.fromarray(result_uint8, mode="RGB")

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate color match parameters."""
        exceptions = []

        # Check that both images are provided
        input_image = self.get_parameter_value("input_image")
        ref_image = self.get_parameter_value("reference_image")
        if input_image is None:
            exceptions.append(ValueError(f"{self.name} - Target image is required"))
        if ref_image is None:
            exceptions.append(ValueError(f"{self.name} - Reference image is required"))

        # Validate strength
        strength = self.get_parameter_value("strength")
        if strength is not None and (strength < self.MIN_STRENGTH or strength > self.MAX_STRENGTH):
            msg = f"{self.name} - Strength must be between {self.MIN_STRENGTH} and {self.MAX_STRENGTH}, got {strength}"
            exceptions.append(ValueError(msg))

        # Validate method
        method = self.get_parameter_value("method")
        if method is not None and method not in self.COLOR_MATCH_METHODS:
            msg = f"{self.name} - Invalid method '{method}'. Must be one of: {', '.join(self.COLOR_MATCH_METHODS)}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get color match parameters."""
        return {
            "method": self.get_parameter_value("method"),
            "strength": self.get_parameter_value("strength"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_colormatch"

    async def aprocess(self) -> None:
        """Main workflow execution method."""
        # Reset execution state and clear status
        self._clear_execution_status()

        # Get input images
        target_image = self.get_parameter_value("input_image")
        ref_image = self.get_parameter_value("reference_image")

        if target_image is None or ref_image is None:
            return

        # Process the images directly for workflow execution
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(target_image, dict):
                target_image = dict_to_image_url_artifact(target_image)

            if isinstance(ref_image, dict):
                ref_image = dict_to_image_url_artifact(ref_image)

            # Load PIL images
            target_pil = load_pil_from_url(target_image.value)
            ref_pil = load_pil_from_url(ref_image.value)

            # Process with current settings
            processed_image = self._process_images(target_pil, ref_pil, **self._get_custom_parameters())

            # Save and set output with proper filename
            filename = self._generate_processed_image_filename("png")
            output_artifact = save_pil_image_with_named_filename(processed_image, filename, "PNG")

            self.set_parameter_value("output", output_artifact)
            self.publish_update_to_parameter("output", output_artifact)

            # Set success status with detailed information
            method = self.get_parameter_value("method")
            strength = self.get_parameter_value("strength")
            success_details = (
                f"Successfully applied color transfer: {self._get_processing_description()}\n"
                f"Method: {method}, Strength: {strength}\n"
                f"Target: {target_pil.width}x{target_pil.height}\n"
                f"Reference: {ref_pil.width}x{ref_pil.height}\n"
                f"Output: {processed_image.width}x{processed_image.height}"
            )
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"{self.name}: Processing failed: {error_message}")

            # Set failure status with detailed error information
            failure_details = f"Color matching failed: {self._get_processing_description()}\nError: {error_message}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {failure_details}")

            # Handle failure based on whether failure output is connected
            self._handle_failure_exception(ValueError(error_message))
            raise
