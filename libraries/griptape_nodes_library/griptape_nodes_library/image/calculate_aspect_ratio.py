from math import gcd
from typing import Any, cast

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.traits.options import Options

# Custom preset constant
CUSTOM_PRESET_NAME = "Custom"

# Preset tuple size constant
PRESET_TUPLE_SIZE = 4

# Aspect ratio presets dictionary
# Format: preset_name -> (width | None, height | None, aspect_width | None, aspect_height | None)
# - If width/height are set: pixel-based preset with specific dimensions
# - If only aspect_width/aspect_height are set: ratio-only preset
# - Custom has all None
ASPECT_RATIO_PRESETS: dict[str, tuple[int | None, int | None, int | None, int | None] | None] = {
    # Custom option - all None
    CUSTOM_PRESET_NAME: None,
    # Pixel presets from sandbox (with calculated ratios)
    "1024x1024": (1024, 1024, 1, 1),
    "896x1152": (896, 1152, 3, 4),
    "832x1216": (832, 1216, 13, 19),
    "768x1344": (768, 1344, 9, 16),
    "640x1536": (640, 1536, 5, 12),
    "1152x896": (1152, 896, 4, 3),
    "1216x832": (1216, 832, 19, 13),
    "1344x768": (1344, 768, 16, 9),
    "1536x640": (1536, 640, 12, 5),
    # Model-native presets from sandbox
    "SD15_512x512": (512, 512, 1, 1),
    "SDXL_1024x1024": (1024, 1024, 1, 1),
    "Flux_768x768": (768, 768, 1, 1),
    # Ratio-only presets (no pixel dimensions specified)
    "1:1": (None, None, 1, 1),
    "2:1": (None, None, 2, 1),
    "1:2": (None, None, 1, 2),
    "3:1": (None, None, 3, 1),
    "1:3": (None, None, 1, 3),
    "4:1": (None, None, 4, 1),
    "1:4": (None, None, 1, 4),
    "5:1": (None, None, 5, 1),
    "1:5": (None, None, 1, 5),
    "2:3": (None, None, 2, 3),
    "3:2": (None, None, 3, 2),
    "3:4": (None, None, 3, 4),
    "4:3": (None, None, 4, 3),
    "4:5": (None, None, 4, 5),
    "5:4": (None, None, 5, 4),
    "5:6": (None, None, 5, 6),
    "6:7": (None, None, 6, 7),
    "7:8": (None, None, 7, 8),
    "8:9": (None, None, 8, 9),
    "9:10": (None, None, 9, 10),
    "5:7": (None, None, 5, 7),
    "7:5": (None, None, 7, 5),
    "5:8": (None, None, 5, 8),
    "9:16": (None, None, 9, 16),
    "16:9": (None, None, 16, 9),
    "9:18": (None, None, 9, 18),
    "9:19": (None, None, 9, 19),
    "9:20": (None, None, 9, 20),
    "9:21": (None, None, 9, 21),
    "21:9": (None, None, 21, 9),
    "9:22": (None, None, 9, 22),
    "9:24": (None, None, 9, 24),
    "9:32": (None, None, 9, 32),
    "10:11": (None, None, 10, 11),
    "10:16": (None, None, 10, 16),
    "16:10": (None, None, 16, 10),
    "11:12": (None, None, 11, 12),
    "12:13": (None, None, 12, 13),
    "12:16": (None, None, 12, 16),
    "16:12": (None, None, 16, 12),
    "13:14": (None, None, 13, 14),
    "14:15": (None, None, 14, 15),
    "15:16": (None, None, 15, 16),
    "18:9": (None, None, 18, 9),
    "19:9": (None, None, 19, 9),
    "20:9": (None, None, 20, 9),
    "22:9": (None, None, 22, 9),
    "24:9": (None, None, 24, 9),
    "32:9": (None, None, 32, 9),
}


class CalculateAspectRatio(SuccessFailureNode):
    """Node for calculating and managing aspect ratios with presets and modifiers."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Lock to prevent recursion during parameter updates
        self._updating_lock = False

        # Add preset parameter
        self._preset_parameter = Parameter(
            name="preset",
            type="str",
            tooltip="Select a preset aspect ratio or 'Custom' for manual configuration",
            default_value="Custom",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            traits={Options(choices=list(ASPECT_RATIO_PRESETS.keys()))},
        )
        self.add_parameter(self._preset_parameter)

        # Working parameters (PROPERTY + OUTPUT only)
        self._width_parameter = Parameter(
            name="width",
            input_types=["int"],
            type="int",
            output_type="int",
            tooltip="Width in pixels",
            default_value=1024,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._width_parameter)

        self._height_parameter = Parameter(
            name="height",
            type="int",
            tooltip="Height in pixels",
            default_value=1024,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._height_parameter)

        self._ratio_str_parameter = Parameter(
            name="ratio_str",
            type="str",
            tooltip="Aspect ratio as string (e.g., '16:9')",
            default_value="1:1",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._ratio_str_parameter)

        self._ratio_decimal_parameter = Parameter(
            name="ratio_decimal",
            type="float",
            tooltip="Aspect ratio as decimal (width/height)",
            default_value=1.0,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._ratio_decimal_parameter)

        # Modifier parameters (INPUT + PROPERTY + OUTPUT)
        self._upscale_value_parameter = Parameter(
            name="upscale_value",
            type="float",
            tooltip="Multiplier for scaling dimensions",
            default_value=1.0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._upscale_value_parameter)

        self._swap_dimensions_parameter = Parameter(
            name="swap_dimensions",
            type="bool",
            tooltip="Swap width and height",
            default_value=False,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self._swap_dimensions_parameter)

        # Output parameters (OUTPUT only)
        self._final_width_parameter = Parameter(
            name="final_width",
            output_type="int",
            settable=False,
            tooltip="Final calculated width after applying modifiers",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self._final_width_parameter)

        self._final_height_parameter = Parameter(
            name="final_height",
            output_type="int",
            settable=False,
            tooltip="Final calculated height after applying modifiers",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self._final_height_parameter)

        # Add status parameters for error reporting
        self._create_status_parameters(
            result_details_tooltip="Details about the aspect ratio calculation result",
            result_details_placeholder="Calculation result details will appear here.",
        )

        # Validate presets configuration
        self._validate_presets()

    def _validate_presets(self) -> None:
        """Validate ASPECT_RATIO_PRESETS structure during initialization."""
        errors = []

        for preset_name, preset_value in ASPECT_RATIO_PRESETS.items():
            preset_error = self._validate_single_preset(preset_name, preset_value)
            if preset_error:
                errors.append(preset_error)

        if errors:
            error_lines = [f"\t* {error}" for error in errors]
            error_message = "Invalid ASPECT_RATIO_PRESETS configuration:\n" + "\n".join(error_lines)
            raise ValueError(error_message)

    def _validate_single_preset(
        self, preset_name: str, preset_value: tuple[int | None, int | None, int | None, int | None] | None
    ) -> str | None:
        """Validate a single preset entry. Returns error message or None if valid."""
        # Custom should be None
        if preset_name == CUSTOM_PRESET_NAME:
            if preset_value is not None:
                return f"Preset '{preset_name}' should have value None."
            return None

        # All other presets must be tuples
        if preset_value is None:
            return f"Preset '{preset_name}' cannot be None (only '{CUSTOM_PRESET_NAME}' can be None)."

        return self._validate_preset_tuple(preset_name, preset_value)

    def _validate_preset_tuple(
        self, preset_name: str, preset_value: tuple[int | None, int | None, int | None, int | None]
    ) -> str | None:
        """Validate the structure and values of a preset tuple."""
        if len(preset_value) != PRESET_TUPLE_SIZE:
            return f"Preset '{preset_name}' must be a tuple with exactly {PRESET_TUPLE_SIZE} elements."

        width, height, aspect_w, aspect_h = preset_value

        # Check for partial specifications
        error = self._validate_preset_completeness(preset_name, width, height, aspect_w, aspect_h)
        if error:
            return error

        # Verify math if both pixels and ratio are specified
        if width is not None and height is not None and aspect_w is not None and aspect_h is not None:
            return self._validate_preset_math(preset_name, width, height, aspect_w, aspect_h)

        return None

    def _validate_preset_completeness(
        self,
        preset_name: str,
        width: int | None,
        height: int | None,
        aspect_w: int | None,
        aspect_h: int | None,
    ) -> str | None:
        """Validate that preset dimensions are complete (both or neither for pixels and ratio)."""
        # Check for partial pixel dimensions
        if (width is None) != (height is None):
            return f"Preset '{preset_name}' has only one pixel dimension specified (need both or neither)."

        # Check for partial ratio dimensions
        if (aspect_w is None) != (aspect_h is None):
            return f"Preset '{preset_name}' has only one aspect ratio dimension specified (need both or neither)."

        # Must have at least pixels OR ratio
        if width is None and aspect_w is None:
            return f"Preset '{preset_name}' must specify either pixel dimensions or aspect ratio."

        return None

    def _validate_preset_math(
        self, preset_name: str, width: int, height: int, aspect_w: int, aspect_h: int
    ) -> str | None:
        """Validate that pixel dimensions match the specified aspect ratio."""
        calculated_ratio = self._calculate_ratio(width, height)
        if calculated_ratio is None:
            return f"Preset '{preset_name}' has invalid pixel dimensions that could not be reduced to a ratio."

        if calculated_ratio != (aspect_w, aspect_h):
            return (
                f"Preset '{preset_name}' has mismatched pixels and ratio: "
                f"{width}x{height} resolves to {calculated_ratio[0]}:{calculated_ratio[1]}, "
                f"not {aspect_w}:{aspect_h}."
            )

        return None

    def process(self) -> None:
        """Main execution logic - just recalculate outputs since validation happens in set_parameter_value."""
        # Reset execution state
        self._clear_execution_status()

        # Recalculate outputs (validation already happened in set_parameter_value)
        try:
            self._calculate_outputs()

            # Success path
            final_width = self.parameter_output_values[self._final_width_parameter.name]
            final_height = self.parameter_output_values[self._final_height_parameter.name]
            success_msg = f"Successfully calculated aspect ratio: {final_width}x{final_height}"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_msg}")
        except Exception as e:
            error_msg = f"Failed to calculate outputs: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_msg}")
            self._clear_output_values()
            self._handle_failure_exception(e)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to add locking logic for preset/working/modifier parameters."""
        # Call parent first to set the value
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        # Early out if locked
        if self._updating_lock:
            return

        # Only process preset, working, or modifier parameters
        managed_param_names = {
            self._preset_parameter.name,
            self._width_parameter.name,
            self._height_parameter.name,
            self._ratio_str_parameter.name,
            self._upscale_value_parameter.name,
            self._swap_dimensions_parameter.name,
        }

        if param_name not in managed_param_names:
            return

        # Acquire lock
        self._updating_lock = True
        try:
            # Handle parameter changes based on which parameter was set
            match param_name:
                case self._preset_parameter.name:
                    self._handle_preset_change(value)
                case self._width_parameter.name:
                    self._handle_width_change(value)
                case self._height_parameter.name:
                    self._handle_height_change(value)
                case self._ratio_str_parameter.name:
                    self._handle_ratio_str_change(value)
                case self._upscale_value_parameter.name | self._swap_dimensions_parameter.name:
                    pass  # Modifiers just need outputs recalculated, which always happens in here.

        finally:
            # Always recalculate final outputs (even if handlers throw)
            try:
                self._calculate_outputs()
                # Success - set status
                final_width = self.parameter_output_values[self._final_width_parameter.name]
                final_height = self.parameter_output_values[self._final_height_parameter.name]
                self._set_status_results(was_successful=True, result_details=f"{final_width}x{final_height}")
            except ValueError as e:
                # Validation error - set failure status
                self._set_status_results(was_successful=False, result_details=str(e))
            finally:
                # Always release lock
                self._updating_lock = False

    def _clear_output_values(self) -> None:
        """Clear all output parameter values."""
        self.parameter_output_values[self._final_width_parameter.name] = None
        self.parameter_output_values[self._final_height_parameter.name] = None

    def _calculate_outputs(self) -> None:
        """Apply modifiers to working parameters and set final outputs."""
        width = self.get_parameter_value(self._width_parameter.name)
        height = self.get_parameter_value(self._height_parameter.name)
        upscale_value = self.get_parameter_value(self._upscale_value_parameter.name)
        swap_dimensions = self.get_parameter_value(self._swap_dimensions_parameter.name)

        # Collect all validation errors
        errors = []

        if width is None:
            errors.append(f"Parameter '{self._width_parameter.name}' was missing or could not be calculated.")
        elif width <= 0:
            errors.append(f"Parameter '{self._width_parameter.name}' must be positive (got {width}).")

        if height is None:
            errors.append(f"Parameter '{self._height_parameter.name}' was missing or could not be calculated.")
        elif height <= 0:
            errors.append(f"Parameter '{self._height_parameter.name}' must be positive (got {height}).")

        if upscale_value is None:
            errors.append(f"Parameter '{self._upscale_value_parameter.name}' was missing or could not be calculated.")
        elif upscale_value < 0:
            errors.append(
                f"Parameter '{self._upscale_value_parameter.name}' must be non-negative (got {upscale_value})."
            )

        # If there are any errors, clear outputs and throw
        if errors:
            self._clear_output_values()
            error_lines = [f"\t* {error}" for error in errors]
            error_message = "Failed due to the following reason(s):\n" + "\n".join(error_lines)
            raise ValueError(error_message)

        # All inputs valid - calculate outputs
        final_width = width
        final_height = height

        if swap_dimensions:
            final_width, final_height = final_height, final_width

        final_width = int(final_width * upscale_value)
        final_height = int(final_height * upscale_value)

        # Success path
        self.parameter_output_values[self._final_width_parameter.name] = final_width
        self.parameter_output_values[self._final_height_parameter.name] = final_height

    def _handle_preset_change(self, preset_name: str) -> None:
        """Handle preset parameter changes - update ALL working parameters."""
        # Custom preset means user is manually setting values - nothing to do
        if preset_name == CUSTOM_PRESET_NAME:
            return

        # Validate preset exists - user could provide any string via input connection
        if preset_name not in ASPECT_RATIO_PRESETS:
            error_msg = f"Unknown preset '{preset_name}'."
            raise ValueError(error_msg)

        preset = ASPECT_RATIO_PRESETS[preset_name]
        if preset is None:
            error_msg = f"Preset '{preset_name}' cannot be applied (only '{CUSTOM_PRESET_NAME}' can be None)."
            raise ValueError(error_msg)

        preset_width, preset_height, preset_aspect_width, preset_aspect_height = preset

        # Case 1: Preset has pixel dimensions specified - use them directly
        if preset_width is not None and preset_height is not None:
            self._apply_pixel_preset(preset_width, preset_height)
        # Case 2: Preset has only ratio specified - calculate pixels from current dimensions
        elif preset_aspect_width is not None and preset_aspect_height is not None:
            self._apply_ratio_preset(preset_aspect_width, preset_aspect_height)

    def _apply_pixel_preset(self, preset_width: int, preset_height: int) -> None:
        """Apply a preset with pixel dimensions specified."""
        self.set_parameter_value(self._width_parameter.name, preset_width)
        self.set_parameter_value(self._height_parameter.name, preset_height)

        # Calculate and update ratio from pixels
        ratio = self._calculate_ratio(preset_width, preset_height)
        if ratio is not None:
            ratio_str = f"{ratio[0]}:{ratio[1]}"
            self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

            ratio_decimal = ratio[0] / ratio[1]
            self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

    def _apply_ratio_preset(self, preset_aspect_width: int, preset_aspect_height: int) -> None:
        """Apply a preset with only ratio specified - calculate pixels from current dimensions."""
        # Get current dimensions
        current_width = self.get_parameter_value(self._width_parameter.name)
        current_height = self.get_parameter_value(self._height_parameter.name)

        # Calculate new dimensions based on which dimension is primary in the ratio
        width_is_primary = preset_aspect_width >= preset_aspect_height
        new_width, new_height = self._calculate_dimensions_from_ratio(
            current_width, current_height, preset_aspect_width, preset_aspect_height, width_is_primary=width_is_primary
        )

        # Update pixel dimensions
        self.set_parameter_value(self._width_parameter.name, new_width)
        self.set_parameter_value(self._height_parameter.name, new_height)

        # Update ratio string and decimal
        ratio_str = f"{preset_aspect_width}:{preset_aspect_height}"
        self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

        ratio_decimal = preset_aspect_width / preset_aspect_height
        self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

    def _calculate_dimensions_from_ratio(
        self,
        current_width: int | None,
        current_height: int | None,
        aspect_width: int,
        aspect_height: int,
        *,
        width_is_primary: bool,
    ) -> tuple[int, int]:
        """Calculate new dimensions from ratio, using available current dimensions."""
        # Calculate new dimensions based on which is primary
        if width_is_primary:
            return self._calculate_width_primary_dimensions(current_width, current_height, aspect_width, aspect_height)

        return self._calculate_height_primary_dimensions(current_width, current_height, aspect_width, aspect_height)

    def _calculate_width_primary_dimensions(
        self, current_width: int | None, current_height: int | None, aspect_width: int, aspect_height: int
    ) -> tuple[int, int]:
        """Calculate dimensions when width is primary in ratio."""
        has_valid_width = current_width is not None and current_width > 0
        has_valid_height = current_height is not None and current_height > 0
        default_size = 1024

        if has_valid_width and has_valid_height:
            width_val = cast("int", current_width)
            height_val = cast("int", current_height)
            larger_dimension = max(width_val, height_val)
            new_width = larger_dimension
            new_height = int(new_width * aspect_height / aspect_width)
        elif has_valid_width:
            width_val = cast("int", current_width)
            new_width = width_val
            new_height = int(new_width * aspect_height / aspect_width)
        elif has_valid_height:
            height_val = cast("int", current_height)
            new_height = height_val
            new_width = int(new_height * aspect_width / aspect_height)
        else:
            new_width = default_size
            new_height = int(new_width * aspect_height / aspect_width)

        return (new_width, new_height)

    def _calculate_height_primary_dimensions(
        self, current_width: int | None, current_height: int | None, aspect_width: int, aspect_height: int
    ) -> tuple[int, int]:
        """Calculate dimensions when height is primary in ratio."""
        has_valid_width = current_width is not None and current_width > 0
        has_valid_height = current_height is not None and current_height > 0
        default_size = 1024

        if has_valid_width and has_valid_height:
            width_val = cast("int", current_width)
            height_val = cast("int", current_height)
            larger_dimension = max(width_val, height_val)
            new_height = larger_dimension
            new_width = int(new_height * aspect_width / aspect_height)
        elif has_valid_height:
            height_val = cast("int", current_height)
            new_height = height_val
            new_width = int(new_height * aspect_width / aspect_height)
        elif has_valid_width:
            width_val = cast("int", current_width)
            new_width = width_val
            new_height = int(new_width * aspect_height / aspect_width)
        else:
            new_height = default_size
            new_width = int(new_height * aspect_width / aspect_height)

        return (new_width, new_height)

    def _handle_width_change(self, width: int) -> None:
        """Handle width parameter changes - update ratio and match preset."""
        height = self.get_parameter_value(self._height_parameter.name)

        # Early out for invalid values
        if width is None or height is None or width <= 0 or height <= 0:
            return

        # Update ratio parameters
        ratio = self._calculate_ratio(width, height)
        if ratio is not None:
            ratio_str = f"{ratio[0]}:{ratio[1]}"
            self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

            ratio_decimal = ratio[0] / ratio[1]
            self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

        # Match to preset
        self._match_preset()

    def _handle_height_change(self, height: int) -> None:
        """Handle height parameter changes - update ratio and match preset."""
        width = self.get_parameter_value(self._width_parameter.name)

        # Early out for invalid values
        if width is None or height is None or width <= 0 or height <= 0:
            return

        # Update ratio parameters
        ratio = self._calculate_ratio(width, height)
        if ratio is not None:
            ratio_str = f"{ratio[0]}:{ratio[1]}"
            self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

            ratio_decimal = ratio[0] / ratio[1]
            self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

        # Match to preset
        self._match_preset()

    def _handle_ratio_str_change(self, ratio_str: str) -> None:
        """Handle ratio_str parameter changes - update decimal and match preset."""
        # Early out for invalid input
        if not ratio_str or ":" not in ratio_str:
            return

        # Parse ratio string (expected format: "width:height")
        try:
            parts = ratio_str.split(":")
            expected_parts_count = 2
            if len(parts) != expected_parts_count:
                return
            aspect_width = int(parts[0].strip())
            aspect_height = int(parts[1].strip())
            if aspect_width <= 0 or aspect_height <= 0:
                return
        except ValueError:
            return

        # Update ratio decimal
        ratio_decimal = aspect_width / aspect_height
        self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

        # Match to preset
        self._match_preset()

    def _match_preset(self) -> None:
        """Match current working parameters to a preset using tiered matching."""
        width = self.get_parameter_value(self._width_parameter.name)
        height = self.get_parameter_value(self._height_parameter.name)

        # Early out for invalid inputs
        if width is None or height is None or width <= 0 or height <= 0:
            self.set_parameter_value(self._preset_parameter.name, "Custom")
            return

        # Calculate current ratio
        current_ratio = self._calculate_ratio(width, height)

        # Tier 1: Exact pixel match
        for preset_name, preset in ASPECT_RATIO_PRESETS.items():
            if preset is None:
                continue
            preset_width, preset_height, _preset_aspect_width, _preset_aspect_height = preset
            if (
                preset_width is not None
                and preset_height is not None
                and preset_width == width
                and preset_height == height
            ):
                self.set_parameter_value(self._preset_parameter.name, preset_name)
                return

        # Tier 2: Ratio-only match (only for presets WITHOUT pixel dimensions)
        if current_ratio is not None:
            for preset_name, preset in ASPECT_RATIO_PRESETS.items():
                if preset is None:
                    continue
                preset_width, preset_height, preset_aspect_width, preset_aspect_height = preset
                # Only match ratio-only presets (no pixel dimensions)
                if (
                    preset_width is None
                    and preset_height is None
                    and preset_aspect_width is not None
                    and preset_aspect_height is not None
                ):
                    preset_ratio = (preset_aspect_width, preset_aspect_height)
                    if current_ratio == preset_ratio:
                        self.set_parameter_value(self._preset_parameter.name, preset_name)
                        return

        # Tier 3: No match - set to Custom (success path)
        self.set_parameter_value(self._preset_parameter.name, "Custom")

    def _calculate_ratio(self, width: int, height: int) -> tuple[int, int] | None:
        """Calculate GCD-reduced ratio from width and height."""
        # Early out for invalid dimensions
        if width <= 0 or height <= 0:
            return None

        divisor = gcd(width, height)
        ratio_width = width // divisor
        ratio_height = height // divisor

        # Success path
        return (ratio_width, ratio_height)
