from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class ResizeImage(BaseImageProcessor):
    """Resize an image using PIL."""

    # Resize mode options
    RESIZE_MODE_OPTIONS = {
        "exact": "Exact size (may distort aspect ratio)",
        "fit": "Fit within dimensions (maintain aspect ratio)",
        "fill": "Fill dimensions (crop to maintain aspect ratio)",
        "percentage": "Resize by percentage",
    }

    def _setup_custom_parameters(self) -> None:
        """Setup resize parameters."""
        # Resize mode parameter
        resize_mode_param = Parameter(
            name="resize_mode",
            type="str",
            default_value="fit",
            tooltip="How to resize the image",
        )
        resize_mode_param.add_trait(Options(choices=list(self.RESIZE_MODE_OPTIONS.keys())))
        self.add_parameter(resize_mode_param)

        # Width parameter
        width_param = Parameter(
            name="width",
            type="int",
            default_value=800,
            tooltip="Target width in pixels",
        )
        width_param.add_trait(Slider(min_val=1, max_val=4000))
        self.add_parameter(width_param)

        # Height parameter
        height_param = Parameter(
            name="height",
            type="int",
            default_value=600,
            tooltip="Target height in pixels",
        )
        height_param.add_trait(Slider(min_val=1, max_val=4000))
        self.add_parameter(height_param)

        # Percentage parameter
        percentage_param = Parameter(
            name="percentage",
            type="float",
            default_value=50.0,
            tooltip="Resize percentage (50.0 = 50% of original size)",
        )
        percentage_param.add_trait(Slider(min_val=1.0, max_val=1000.0))
        self.add_parameter(percentage_param)

        # Background color parameter (for fill mode)
        self.add_parameter(
            Parameter(
                name="background_color",
                type="str",
                default_value="#000000",
                tooltip="Background color for fill mode (hex color code)",
            )
        )

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        resize_mode = self.get_parameter_value("resize_mode") or "fit"

        if resize_mode == "percentage":
            percentage = self.get_parameter_value("percentage") or 50.0
            return f"Resizing image to {percentage}% of original size"
        width = self.get_parameter_value("width") or 800
        height = self.get_parameter_value("height") or 600
        return f"Resizing image to {width}x{height} using {resize_mode} mode"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Resize the image."""
        resize_mode = kwargs.get("resize_mode", "fit")
        width = kwargs.get("width", 800)
        height = kwargs.get("height", 600)
        percentage = kwargs.get("percentage", 50.0)
        background_color = kwargs.get("background_color", "#000000")
        resampling = self._get_resampling_method()

        original_width, original_height = image.size

        if resize_mode == "percentage":
            # Resize by percentage
            new_width = int(original_width * percentage / 100.0)
            new_height = int(original_height * percentage / 100.0)
            resized_image = image.resize((new_width, new_height), resampling)

        elif resize_mode == "exact":
            # Resize to exact dimensions (may distort)
            resized_image = image.resize((width, height), resampling)

        elif resize_mode == "fit":
            # Fit within dimensions (maintain aspect ratio)
            resized_image = image.copy()
            resized_image.thumbnail((width, height), resampling)

        elif resize_mode == "fill":
            # Fill dimensions (crop to maintain aspect ratio)
            # Calculate scale to cover the target dimensions
            scale_x = width / original_width
            scale_y = height / original_height
            scale = max(scale_x, scale_y)  # Use larger scale to ensure coverage

            # Resize to cover
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            resized_image = image.resize((new_width, new_height), resampling)

            # Crop to exact dimensions
            left = (new_width - width) // 2
            top = (new_height - height) // 2
            right = left + width
            bottom = top + height
            resized_image = resized_image.crop((left, top, right, bottom))

        else:
            # Default to fit mode
            resized_image = image.copy()
            resized_image.thumbnail((width, height), resampling)

        return resized_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get resize parameters."""
        return {
            "resize_mode": self.get_parameter_value("resize_mode") or "fit",
            "width": self.get_parameter_value("width") or 800,
            "height": self.get_parameter_value("height") or 600,
            "percentage": self.get_parameter_value("percentage") or 50.0,
            "background_color": self.get_parameter_value("background_color") or "#000000",
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        resize_mode = kwargs.get("resize_mode", "fit")

        if resize_mode == "percentage":
            percentage = kwargs.get("percentage", 50.0)
            return f"_resized_{percentage}pct"
        width = kwargs.get("width", 800)
        height = kwargs.get("height", 600)
        return f"_resized_{width}x{height}_{resize_mode}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate resize parameters."""
        exceptions = []

        # Validate width
        width = self.get_parameter_value("width")
        if width is not None:
            if not isinstance(width, int):
                msg = f"{self.name}: Width must be an integer"
                exceptions.append(ValueError(msg))
            elif width <= 0:
                msg = f"{self.name}: Width must be positive"
                exceptions.append(ValueError(msg))

        # Validate height
        height = self.get_parameter_value("height")
        if height is not None:
            if not isinstance(height, int):
                msg = f"{self.name}: Height must be an integer"
                exceptions.append(ValueError(msg))
            elif height <= 0:
                msg = f"{self.name}: Height must be positive"
                exceptions.append(ValueError(msg))

        # Validate percentage
        percentage = self.get_parameter_value("percentage")
        if percentage is not None:
            if not isinstance(percentage, (int, float)):
                msg = f"{self.name}: Percentage must be a number"
                exceptions.append(ValueError(msg))
            elif percentage <= 0 or percentage > 1000:
                msg = f"{self.name}: Percentage must be between 0 and 1000"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None
