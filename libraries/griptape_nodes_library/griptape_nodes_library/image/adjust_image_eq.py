from typing import Any

from PIL import Image, ImageEnhance

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor
from griptape_nodes_library.utils.image_utils import (
    dict_to_image_url_artifact,
    load_pil_from_url,
    save_pil_image_with_named_filename,
)


class AdjustImageEQ(BaseImageProcessor):
    """Adjust image brightness and contrast using PIL's ImageEnhance."""

    # Brightness constants
    MIN_BRIGHTNESS = 0.0
    MAX_BRIGHTNESS = 3.0
    DEFAULT_BRIGHTNESS = 1.0

    # Contrast constants
    MIN_CONTRAST = 0.0
    MAX_CONTRAST = 3.0
    DEFAULT_CONTRAST = 1.0

    # Saturation constants
    MIN_SATURATION = 0.0
    MAX_SATURATION = 3.0
    DEFAULT_SATURATION = 1.0

    # Gamma constants
    MIN_GAMMA = 0.1
    MAX_GAMMA = 10.0
    DEFAULT_GAMMA = 1.0

    def _setup_custom_parameters(self) -> None:
        """Setup brightness/contrast-specific parameters."""
        with ParameterGroup(name="adjustment_settings", ui_options={"collapsed": False}) as adjustment_group:
            # Brightness parameter
            brightness_param = Parameter(
                name="brightness",
                type="float",
                default_value=self.DEFAULT_BRIGHTNESS,
                tooltip=f"Brightness adjustment ({self.MIN_BRIGHTNESS}-{self.MAX_BRIGHTNESS}, 1.0 = normal)",
            )
            brightness_param.add_trait(Slider(min_val=self.MIN_BRIGHTNESS, max_val=self.MAX_BRIGHTNESS))
            self.add_parameter(brightness_param)

            # Contrast parameter
            contrast_param = Parameter(
                name="contrast",
                type="float",
                default_value=self.DEFAULT_CONTRAST,
                tooltip=f"Contrast adjustment ({self.MIN_CONTRAST}-{self.MAX_CONTRAST}, 1.0 = normal)",
            )
            contrast_param.add_trait(Slider(min_val=self.MIN_CONTRAST, max_val=self.MAX_CONTRAST))
            self.add_parameter(contrast_param)

            # Saturation parameter
            saturation_param = Parameter(
                name="saturation",
                type="float",
                default_value=self.DEFAULT_SATURATION,
                tooltip=f"Saturation adjustment ({self.MIN_SATURATION}-{self.MAX_SATURATION}, 1.0 = normal)",
            )
            saturation_param.add_trait(Slider(min_val=self.MIN_SATURATION, max_val=self.MAX_SATURATION))
            self.add_parameter(saturation_param)

            # Gamma parameter
            gamma_param = Parameter(
                name="gamma",
                type="float",
                default_value=self.DEFAULT_GAMMA,
                tooltip=f"Gamma adjustment ({self.MIN_GAMMA}-{self.MAX_GAMMA}, 1.0 = normal)",
            )
            gamma_param.add_trait(Slider(min_val=self.MIN_GAMMA, max_val=self.MAX_GAMMA))
            self.add_parameter(gamma_param)

        self.add_node_element(adjustment_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process image automatically when connected or when EQ parameters change."""
        if parameter.name == "input_image" and value is not None:
            # Process the image immediately when connected
            self._process_image_immediately(value)
        elif parameter.name in ["brightness", "contrast", "saturation", "gamma"]:
            # Process the image when EQ parameters change (for live preview)
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

            # Process with current EQ settings
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
        return "image EQ adjustment (brightness, contrast, saturation, gamma)"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image by adjusting brightness, contrast, saturation, and gamma."""
        brightness = kwargs.get("brightness", self.DEFAULT_BRIGHTNESS)
        contrast = kwargs.get("contrast", self.DEFAULT_CONTRAST)
        saturation = kwargs.get("saturation", self.DEFAULT_SATURATION)
        gamma = kwargs.get("gamma", self.DEFAULT_GAMMA)

        # Debug logging
        logger.debug(
            f"{self.name}: Processing image with brightness={brightness}, contrast={contrast}, saturation={saturation}, gamma={gamma}"
        )

        # Apply brightness adjustment
        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(pil_image)
            pil_image = enhancer.enhance(brightness)

        # Apply contrast adjustment
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(pil_image)
            pil_image = enhancer.enhance(contrast)

        # Apply saturation adjustment
        if saturation != 1.0:
            enhancer = ImageEnhance.Color(pil_image)
            pil_image = enhancer.enhance(saturation)

        # Apply gamma adjustment
        if gamma != 1.0:
            # Debug logging
            logger.debug(f"{self.name}: Applying gamma correction with gamma={gamma}, image_mode={pil_image.mode}")

            # Use the proper gamma correction method from PIL documentation
            # Based on: https://linuxtut.com/en/145d858eff3c505c100a/
            def create_gamma_table(gamma_value: float, gain: float = 1.0) -> list[int]:
                """Create gamma correction lookup table following PIL documentation."""
                return [min(255, int((x / 255.0) ** (1.0 / gamma_value) * gain * 255.0)) for x in range(256)]

            # Create lookup table for gamma correction
            gamma_table = create_gamma_table(gamma, gain=1.0)

            # Debug: Check if lookup table is actually changing values
            logger.debug(
                f"{self.name}: Gamma table sample - input 0->{gamma_table[0]}, 128->{gamma_table[128]}, 255->{gamma_table[255]}"
            )

            # Handle different image modes
            if pil_image.mode == "RGBA":
                # For RGBA images, apply gamma to RGB channels only, preserve alpha
                rgb_image = pil_image.convert("RGB")
                # Create combined lookup table for RGB channels
                combined_table = gamma_table + gamma_table + gamma_table
                gamma_corrected_rgb = rgb_image.point(combined_table)
                # Convert back to RGBA and preserve original alpha
                gamma_corrected_image = gamma_corrected_rgb.convert("RGBA")
                # Copy original alpha channel
                original_alpha = pil_image.getchannel("A")
                gamma_corrected_image.putalpha(original_alpha)
                pil_image = gamma_corrected_image
            elif pil_image.mode == "RGB":
                # For RGB images, create combined lookup table for all channels
                combined_table = gamma_table + gamma_table + gamma_table
                pil_image = pil_image.point(combined_table)
            elif pil_image.mode == "L":
                # For grayscale images, use single channel table
                pil_image = pil_image.point(gamma_table)
            else:
                # For other modes, convert to RGB first
                rgb_image = pil_image.convert("RGB")
                combined_table = gamma_table + gamma_table + gamma_table
                gamma_corrected_rgb = rgb_image.point(combined_table)
                pil_image = gamma_corrected_rgb.convert(pil_image.mode)

        return pil_image

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate EQ parameters."""
        exceptions = []

        brightness = self.get_parameter_value("brightness")
        if brightness is not None and (brightness < self.MIN_BRIGHTNESS or brightness > self.MAX_BRIGHTNESS):
            msg = f"{self.name} - Brightness must be between {self.MIN_BRIGHTNESS} and {self.MAX_BRIGHTNESS}, got {brightness}"
            exceptions.append(ValueError(msg))

        contrast = self.get_parameter_value("contrast")
        if contrast is not None and (contrast < self.MIN_CONTRAST or contrast > self.MAX_CONTRAST):
            msg = f"{self.name} - Contrast must be between {self.MIN_CONTRAST} and {self.MAX_CONTRAST}, got {contrast}"
            exceptions.append(ValueError(msg))

        saturation = self.get_parameter_value("saturation")
        if saturation is not None and (saturation < self.MIN_SATURATION or saturation > self.MAX_SATURATION):
            msg = f"{self.name} - Saturation must be between {self.MIN_SATURATION} and {self.MAX_SATURATION}, got {saturation}"
            exceptions.append(ValueError(msg))

        gamma = self.get_parameter_value("gamma")
        if gamma is not None and (gamma < self.MIN_GAMMA or gamma > self.MAX_GAMMA):
            msg = f"{self.name} - Gamma must be between {self.MIN_GAMMA} and {self.MAX_GAMMA}, got {gamma}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get EQ parameters."""
        return {
            "brightness": self.get_parameter_value("brightness"),
            "contrast": self.get_parameter_value("contrast"),
            "saturation": self.get_parameter_value("saturation"),
            "gamma": self.get_parameter_value("gamma"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_eq"
