from typing import Any

from PIL import Image, ImageFilter

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class ApplyBlur(BaseImageProcessor):
    """Apply blur effects to an image using PIL's ImageFilter."""

    # Blur type options
    BLUR_OPTIONS = {
        "gaussian": "Gaussian Blur (smooth, natural)",
        "box": "Box Blur (fast, uniform)",
        "unsharp": "Unsharp Mask (sharpen with blur)",
    }

    def _setup_custom_parameters(self) -> None:
        """Setup blur parameters."""
        # Blur type parameter
        blur_type_param = Parameter(
            name="blur_type",
            type="str",
            default_value="gaussian",
            tooltip="Type of blur to apply",
        )
        blur_type_param.add_trait(Options(choices=list(self.BLUR_OPTIONS.keys())))
        self.add_parameter(blur_type_param)

        # Blur radius parameter
        radius_param = Parameter(
            name="radius",
            type="int",
            default_value=2,
            tooltip="Blur radius (1-10). Higher values create more blur.",
        )
        radius_param.add_trait(Slider(min_val=1, max_val=50))
        self.add_parameter(radius_param)

        # Percent parameter for unsharp mask
        percent_param = Parameter(
            name="percent",
            type="int",
            default_value=150,
            tooltip="Percent for unsharp mask (100-200). Higher values create more sharpening.",
        )
        percent_param.add_trait(Slider(min_val=100, max_val=200))
        self.add_parameter(percent_param)

        # Threshold parameter for unsharp mask
        threshold_param = Parameter(
            name="threshold",
            type="int",
            default_value=3,
            tooltip="Threshold for unsharp mask (0-255). Lower values affect more pixels.",
        )
        threshold_param.add_trait(Slider(min_val=0, max_val=255))
        self.add_parameter(threshold_param)

        # Initialize parameter visibility based on default blur type
        self._update_parameter_visibility("gaussian")

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        blur_type = self.get_parameter_value("blur_type") or "gaussian"
        radius = self.get_parameter_value("radius") or 2
        return f"Applying {blur_type} blur with radius {radius}"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Apply blur effect to the image."""
        blur_type = kwargs.get("blur_type", "gaussian")
        radius = kwargs.get("radius", 2)
        percent = kwargs.get("percent", 150)
        threshold = kwargs.get("threshold", 3)

        if blur_type == "gaussian":
            # Apply Gaussian blur
            filtered_image = image.filter(ImageFilter.GaussianBlur(radius=radius))
        elif blur_type == "box":
            # Apply box blur
            filtered_image = image.filter(ImageFilter.BoxBlur(radius=radius))
        elif blur_type == "unsharp":
            # Apply unsharp mask (sharpen with blur)
            filtered_image = image.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
        else:
            # Default to Gaussian blur
            filtered_image = image.filter(ImageFilter.GaussianBlur(radius=radius))

        return filtered_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get blur parameters."""
        return {
            "blur_type": self.get_parameter_value("blur_type") or "gaussian",
            "radius": self.get_parameter_value("radius") or 2,
            "percent": self.get_parameter_value("percent") or 150,
            "threshold": self.get_parameter_value("threshold") or 3,
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        blur_type = kwargs.get("blur_type", "gaussian")
        radius = kwargs.get("radius", 2)
        return f"_blur_{blur_type}_{radius}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate blur parameters."""
        exceptions = []

        # Validate radius
        radius = self.get_parameter_value("radius")
        if radius is not None:
            if not isinstance(radius, int):
                msg = f"{self.name}: Radius must be an integer"
                exceptions.append(ValueError(msg))
            elif radius < 1 or radius > 10:
                msg = f"{self.name}: Radius must be between 1 and 10"
                exceptions.append(ValueError(msg))

        # Validate percent (for unsharp mask)
        percent = self.get_parameter_value("percent")
        if percent is not None:
            if not isinstance(percent, int):
                msg = f"{self.name}: Percent must be an integer"
                exceptions.append(ValueError(msg))
            elif percent < 100 or percent > 200:
                msg = f"{self.name}: Percent must be between 100 and 200"
                exceptions.append(ValueError(msg))

        # Validate threshold (for unsharp mask)
        threshold = self.get_parameter_value("threshold")
        if threshold is not None:
            if not isinstance(threshold, int):
                msg = f"{self.name}: Threshold must be an integer"
                exceptions.append(ValueError(msg))
            elif threshold < 0 or threshold > 255:
                msg = f"{self.name}: Threshold must be between 0 and 255"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Run processing after parameter values are set for real-time feedback."""
        # Handle blur type changes to show/hide relevant parameters
        if parameter.name == "blur_type":
            self._update_parameter_visibility(value)

        # Only process if we have an input image and the parameter is one of our blur parameters
        if parameter.name in ["blur_type", "radius", "percent", "threshold"]:
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                try:
                    # Run the processing to update the output
                    self.process()
                except Exception as e:
                    # Log error but don't crash the UI
                    from griptape_nodes.retained_mode.griptape_nodes import logger

                    logger.warning(f"{self.name}: Error during live blur adjustment: {e}")

        return super().after_value_set(parameter, value)

    def _update_parameter_visibility(self, blur_type: str) -> None:
        """Show/hide parameters based on the selected blur type."""
        # Always show radius (used by all blur types)
        self.show_parameter_by_name("radius")

        # Show percent and threshold only for unsharp mask
        if blur_type == "unsharp":
            self.show_parameter_by_name("percent")
            self.show_parameter_by_name("threshold")
        else:
            # Hide percent and threshold for gaussian and box blur
            self.hide_parameter_by_name("percent")
            self.hide_parameter_by_name("threshold")
