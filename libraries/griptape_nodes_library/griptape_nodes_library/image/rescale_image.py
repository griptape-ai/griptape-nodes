from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class RescaleImage(BaseImageProcessor):
    """Rescale an image with different resize modes and resample filters."""

    # Resize mode constants
    RESIZE_MODE_WIDTH = "width"
    RESIZE_MODE_HEIGHT = "height"
    RESIZE_MODE_PERCENTAGE = "percentage"

    # Target size constants (for width/height modes)
    MIN_TARGET_SIZE = 1
    MAX_TARGET_SIZE = 8000  # Reasonable max for most use cases
    DEFAULT_TARGET_SIZE = 1000

    # Percentage scale constants
    MIN_PERCENTAGE_SCALE = 1
    MAX_PERCENTAGE_SCALE = 500  # 500% = 5x size
    DEFAULT_PERCENTAGE_SCALE = 100  # 100% = original size

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "resize_mode":
            if value == self.RESIZE_MODE_PERCENTAGE:
                self.show_parameter_by_name("percentage_scale")
                self.hide_parameter_by_name("target_size")
            else:
                self.hide_parameter_by_name("percentage_scale")
                self.show_parameter_by_name("target_size")
        return super().after_value_set(parameter, value)

    def _setup_custom_parameters(self) -> None:
        """Setup rescale-specific parameters."""
        with ParameterGroup(name="rescale_settings", ui_options={"collapsed": False}) as rescale_group:
            # Resize mode parameter
            resize_mode_param = Parameter(
                name="resize_mode",
                type="str",
                default_value=self.RESIZE_MODE_PERCENTAGE,
                tooltip="How to resize the image: by width, height, or percentage",
            )
            resize_mode_param.add_trait(
                Options(
                    choices=[
                        self.RESIZE_MODE_WIDTH,
                        self.RESIZE_MODE_HEIGHT,
                        self.RESIZE_MODE_PERCENTAGE,
                    ]
                )
            )
            self.add_parameter(resize_mode_param)

            # Target size parameter (for width/height modes)
            target_size_param = Parameter(
                name="target_size",
                type="int",
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target size in pixels for width/height modes ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_size_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))
            self.add_parameter(target_size_param)
            self.hide_parameter_by_name("target_size")

            # Percentage scale parameter (for percentage mode)
            percentage_scale_param = Parameter(
                name="percentage_scale",
                input_types=["int", "float"],
                type="int",
                default_value=self.DEFAULT_PERCENTAGE_SCALE,
                tooltip=f"Scale factor as percentage ({self.MIN_PERCENTAGE_SCALE}-{self.MAX_PERCENTAGE_SCALE}%, 100% = original size)",
            )
            percentage_scale_param.add_trait(
                Slider(min_val=self.MIN_PERCENTAGE_SCALE, max_val=self.MAX_PERCENTAGE_SCALE)
            )
            self.add_parameter(percentage_scale_param)

            # Resample filter parameter
            resample_filter_param = Parameter(
                name="resample_filter",
                type="str",
                default_value="lanczos",
                tooltip="Resample filter for resizing (higher quality = slower processing)",
            )
            resample_filter_param.add_trait(
                Options(choices=["nearest", "box", "bilinear", "hamming", "bicubic", "lanczos"])
            )
            self.add_parameter(resample_filter_param)

        self.add_node_element(rescale_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "image rescaling"

    def _process_image(self, pil_image: Image.Image, **kwargs) -> Image.Image:
        """Process the PIL image by rescaling it."""
        resize_mode = kwargs.get("resize_mode", self.RESIZE_MODE_PERCENTAGE)
        target_size = kwargs.get("target_size", self.DEFAULT_TARGET_SIZE)
        percentage_scale = kwargs.get("percentage_scale", self.DEFAULT_PERCENTAGE_SCALE)
        resample_filter = kwargs.get("resample_filter", "lanczos")

        # Get the resample filter constant
        resample_constant = self._get_resample_constant(resample_filter)

        # Calculate new dimensions based on resize mode
        if resize_mode == self.RESIZE_MODE_WIDTH:
            # Resize by width, maintain aspect ratio
            ratio = target_size / pil_image.width
            new_width = target_size
            new_height = int(pil_image.height * ratio)
        elif resize_mode == self.RESIZE_MODE_HEIGHT:
            # Resize by height, maintain aspect ratio
            ratio = target_size / pil_image.height
            new_width = int(pil_image.width * ratio)
            new_height = target_size
        elif resize_mode == self.RESIZE_MODE_PERCENTAGE:
            # Resize by percentage scale
            scale_factor = percentage_scale / 100.0
            new_width = int(pil_image.width * scale_factor)
            new_height = int(pil_image.height * scale_factor)
        else:
            msg = f"{self.name} - Invalid resize mode: {resize_mode}"
            raise ValueError(msg)

        # Ensure minimum dimensions
        new_width = max(1, new_width)
        new_height = max(1, new_height)

        # Resize the image
        resized_image = pil_image.resize((new_width, new_height), resample_constant)

        return resized_image

    def _get_resample_constant(self, filter_name: str) -> int:
        """Get the PIL resample constant for the given filter name."""
        filter_map = {
            "nearest": Image.Resampling.NEAREST,
            "box": Image.Resampling.BOX,
            "bilinear": Image.Resampling.BILINEAR,
            "hamming": Image.Resampling.HAMMING,
            "bicubic": Image.Resampling.BICUBIC,
            "lanczos": Image.Resampling.LANCZOS,
        }
        return filter_map.get(filter_name, Image.Resampling.LANCZOS)

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate rescale parameters."""
        exceptions = []

        resize_mode = self.get_parameter_value("resize_mode")
        target_size = self.get_parameter_value("target_size")
        percentage_scale = self.get_parameter_value("percentage_scale")

        # Validate target_size for width/height modes
        if (
            resize_mode in [self.RESIZE_MODE_WIDTH, self.RESIZE_MODE_HEIGHT]
            and target_size is not None
            and (target_size < self.MIN_TARGET_SIZE or target_size > self.MAX_TARGET_SIZE)
        ):
            msg = f"{self.name} - Target size must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_size}"
            exceptions.append(ValueError(msg))

        # Validate percentage_scale for percentage mode
        if (
            resize_mode == self.RESIZE_MODE_PERCENTAGE
            and percentage_scale is not None
            and (percentage_scale < self.MIN_PERCENTAGE_SCALE or percentage_scale > self.MAX_PERCENTAGE_SCALE)
        ):
            msg = f"{self.name} - Percentage scale must be between {self.MIN_PERCENTAGE_SCALE} and {self.MAX_PERCENTAGE_SCALE}, got {percentage_scale}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get rescale parameters."""
        return {
            "resize_mode": self.get_parameter_value("resize_mode"),
            "target_size": self.get_parameter_value("target_size"),
            "percentage_scale": self.get_parameter_value("percentage_scale"),
            "resample_filter": self.get_parameter_value("resample_filter"),
        }

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get output filename suffix."""
        return "_rescaled"
