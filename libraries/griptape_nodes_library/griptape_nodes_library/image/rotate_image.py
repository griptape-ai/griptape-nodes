from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.image.base_image_processor import BaseImageProcessor


class RotateImage(BaseImageProcessor):
    """Rotate an image using PIL."""

    # Rotation options
    ROTATION_OPTIONS = {
        "90": "90° clockwise",
        "180": "180° (upside down)",
        "270": "270° clockwise (90° counter-clockwise)",
        "custom": "Custom angle",
    }

    def _setup_custom_parameters(self) -> None:
        """Setup rotation parameters."""
        # Rotation type parameter
        rotation_type_param = Parameter(
            name="rotation_type",
            type="str",
            default_value="90",
            tooltip="Type of rotation to apply",
        )
        rotation_type_param.add_trait(Options(choices=list(self.ROTATION_OPTIONS.keys())))
        self.add_parameter(rotation_type_param)

        # Custom angle parameter
        custom_angle_param = Parameter(
            name="custom_angle",
            type="float",
            default_value=45.0,
            tooltip="Custom rotation angle in degrees (positive = clockwise, negative = counter-clockwise)",
        )
        custom_angle_param.add_trait(Slider(min_val=-360.0, max_val=360.0))
        self.add_parameter(custom_angle_param)

        # Expand parameter
        self.add_parameter(
            Parameter(
                name="expand",
                type="bool",
                default_value=True,
                tooltip="Expand the image to fit the rotated content (may increase image size)",
            )
        )

        # Initialize parameter visibility based on default rotation type
        self._update_parameter_visibility("90")

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        rotation_type = self.get_parameter_value("rotation_type") or "90"
        expand = self.get_parameter_value("expand")

        if rotation_type == "custom":
            custom_angle = self.get_parameter_value("custom_angle") or 45.0
            return f"Rotating image by {custom_angle}° (expand: {expand})"
        angle = int(rotation_type)
        return f"Rotating image by {angle}° (expand: {expand})"

    def _process_image(self, image: Image.Image, **kwargs) -> Image.Image:
        """Rotate the image."""
        rotation_type = kwargs.get("rotation_type", "90")
        custom_angle = kwargs.get("custom_angle", 45.0)
        expand = kwargs.get("expand", True)

        if rotation_type == "custom":
            # Use custom angle
            rotated_image = image.rotate(-custom_angle, expand=expand, resample=Image.Resampling.BICUBIC)
        else:
            # Use predefined angles
            angle = int(rotation_type)
            rotated_image = image.rotate(-angle, expand=expand, resample=Image.Resampling.BICUBIC)

        return rotated_image

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get rotation parameters."""
        return {
            "rotation_type": self.get_parameter_value("rotation_type") or "90",
            "custom_angle": self.get_parameter_value("custom_angle") or 45.0,
            "expand": self.get_parameter_value("expand") or True,
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        rotation_type = kwargs.get("rotation_type", "90")
        expand = kwargs.get("expand", True)

        if rotation_type == "custom":
            custom_angle = kwargs.get("custom_angle", 45.0)
            return f"_rotated_{custom_angle}_{'expand' if expand else 'crop'}"
        return f"_rotated_{rotation_type}_{'expand' if expand else 'crop'}"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate rotation parameters."""
        exceptions = []

        # Validate custom angle
        custom_angle = self.get_parameter_value("custom_angle")
        if custom_angle is not None:
            if not isinstance(custom_angle, (int, float)):
                msg = f"{self.name}: Custom angle must be a number"
                exceptions.append(ValueError(msg))
            elif custom_angle < -360 or custom_angle > 360:
                msg = f"{self.name}: Custom angle must be between -360 and 360 degrees"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Run processing after parameter values are set for real-time feedback."""
        # Handle rotation type changes to show/hide relevant parameters
        if parameter.name == "rotation_type":
            self._update_parameter_visibility(value)

        # Only process if we have an input image and the parameter is one of our rotation parameters
        if parameter.name in ["rotation_type", "custom_angle", "expand"]:
            input_image = self.get_parameter_value("input_image")
            if input_image is not None:
                try:
                    # Run the processing to update the output
                    self.process()
                except Exception as e:
                    # Log error but don't crash the UI
                    from griptape_nodes.retained_mode.griptape_nodes import logger

                    logger.warning(f"{self.name}: Error during live rotation: {e}")

        return super().after_value_set(parameter, value)

    def _update_parameter_visibility(self, rotation_type: str) -> None:
        """Show/hide parameters based on the selected rotation type."""
        # Show custom angle only when custom rotation is selected
        if rotation_type == "custom":
            self.show_parameter_by_name("custom_angle")
        else:
            # Hide custom angle for predefined rotations
            self.hide_parameter_by_name("custom_angle")
