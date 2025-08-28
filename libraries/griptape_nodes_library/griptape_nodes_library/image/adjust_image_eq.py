from typing import Any

from PIL import Image, ImageEnhance

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class AdjustImageEQ(BaseImageProcessor):
    """Adjust brightness, contrast, and saturation of an image using PIL's ImageEnhance."""

    def _setup_custom_parameters(self) -> None:
        """Setup image equalizer parameters."""
        # Brightness parameter
        brightness_param = Parameter(
            name="brightness",
            type="float",
            default_value=1.0,
            tooltip="Brightness adjustment. 1.0 = original brightness, 0.5 = 50% darker, 2.0 = 100% brighter",
        )
        brightness_param.add_trait(Slider(min_val=0.0, max_val=3.0))
        self.add_parameter(brightness_param)

        # Contrast parameter
        contrast_param = Parameter(
            name="contrast",
            type="float",
            default_value=1.0,
            tooltip="Contrast adjustment. 1.0 = original contrast, 0.5 = 50% less contrast, 2.0 = 100% more contrast",
        )
        contrast_param.add_trait(Slider(min_val=0.0, max_val=3.0))
        self.add_parameter(contrast_param)

        # Saturation parameter
        saturation_param = Parameter(
            name="saturation",
            type="float",
            default_value=1.0,
            tooltip="Saturation adjustment. 1.0 = original saturation, 0.0 = grayscale, 2.0 = 100% more saturated",
        )
        saturation_param.add_trait(Slider(min_val=0.0, max_val=3.0))
        self.add_parameter(saturation_param)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        brightness = self.get_parameter_value("brightness") or 1.0
        contrast = self.get_parameter_value("contrast") or 1.0
        saturation = self.get_parameter_value("saturation") or 1.0

        adjustments = []
        if brightness != 1.0:
            adjustments.append(f"brightness: {brightness}")
        if contrast != 1.0:
            adjustments.append(f"contrast: {contrast}")
        if saturation != 1.0:
            adjustments.append(f"saturation: {saturation}")

        if not adjustments:
            return "No adjustments applied (all values at 1.0)"

        return f"Adjusting image: {', '.join(adjustments)}"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Apply brightness, contrast, and saturation adjustments to the image."""
        brightness = kwargs.get("brightness", 1.0)
        contrast = kwargs.get("contrast", 1.0)
        saturation = kwargs.get("saturation", 1.0)

        processed_image = image

        # Apply brightness adjustment if needed
        if brightness != 1.0:
            brightness_enhancer = ImageEnhance.Brightness(processed_image)
            processed_image = brightness_enhancer.enhance(brightness)

        # Apply contrast adjustment if needed
        if contrast != 1.0:
            contrast_enhancer = ImageEnhance.Contrast(processed_image)
            processed_image = contrast_enhancer.enhance(contrast)

        # Apply saturation adjustment if needed
        if saturation != 1.0:
            color_enhancer = ImageEnhance.Color(processed_image)
            processed_image = color_enhancer.enhance(saturation)

        return processed_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get all EQ parameters."""
        return {
            "brightness": self.get_parameter_value("brightness") or 1.0,
            "contrast": self.get_parameter_value("contrast") or 1.0,
            "saturation": self.get_parameter_value("saturation") or 1.0,
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        brightness = kwargs.get("brightness", 1.0)
        contrast = kwargs.get("contrast", 1.0)
        saturation = kwargs.get("saturation", 1.0)

        # Only include non-default values in suffix
        parts = []
        if brightness != 1.0:
            parts.append(f"b{brightness}")
        if contrast != 1.0:
            parts.append(f"c{contrast}")
        if saturation != 1.0:
            parts.append(f"s{saturation}")

        if not parts:
            return "_eq_default"

        return f"_eq_{'_'.join(parts)}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate all EQ parameters."""
        exceptions = []

        # Validate brightness
        brightness = self.get_parameter_value("brightness")
        if brightness is not None:
            if not isinstance(brightness, (int, float)):
                msg = f"{self.name}: Brightness must be a number"
                exceptions.append(ValueError(msg))
            elif brightness < 0:
                msg = f"{self.name}: Brightness cannot be negative"
                exceptions.append(ValueError(msg))

        # Validate contrast
        contrast = self.get_parameter_value("contrast")
        if contrast is not None:
            if not isinstance(contrast, (int, float)):
                msg = f"{self.name}: Contrast must be a number"
                exceptions.append(ValueError(msg))
            elif contrast < 0:
                msg = f"{self.name}: Contrast cannot be negative"
                exceptions.append(ValueError(msg))

        # Validate saturation
        saturation = self.get_parameter_value("saturation")
        if saturation is not None:
            if not isinstance(saturation, (int, float)):
                msg = f"{self.name}: Saturation must be a number"
                exceptions.append(ValueError(msg))
            elif saturation < 0:
                msg = f"{self.name}: Saturation cannot be negative"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Run processing after parameter values are set for real-time feedback."""
        # Only process if we have an input image and the parameter is one of our adjustment parameters
        if parameter.name in ["brightness", "contrast", "saturation"]:
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                try:
                    # Run the processing to update the output
                    self.process()
                except Exception as e:
                    # Log error but don't crash the UI
                    from griptape_nodes.retained_mode.griptape_nodes import logger

                    logger.warning(f"{self.name}: Error during live adjustment: {e}")

        return super().after_value_set(parameter, value)
