from math import gcd
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.traits.options import Options


class AspectRatioPreset(NamedTuple):
    """Represents an aspect ratio preset with optional pixel dimensions and aspect ratio."""

    width: int | None
    height: int | None
    aspect_width: int | None
    aspect_height: int | None


# Custom preset constant
CUSTOM_PRESET_NAME = "Custom"

# Preset tuple size constant
PRESET_TUPLE_SIZE = 4

# Aspect ratio presets dictionary
# Format: preset_name -> AspectRatioPreset(width, height, aspect_width, aspect_height)
# - If width/height are set: pixel-based preset with specific dimensions
# - If only aspect_width/aspect_height are set: ratio-only preset
# - Custom has all None
# Note: Regular tuples are used but type checker sees them as AspectRatioPreset (NamedTuples are tuple-compatible)
ASPECT_RATIO_PRESETS: dict[str, tuple[int | None, int | None, int | None, int | None] | None] = {
    # Custom option - all None
    CUSTOM_PRESET_NAME: None,
    # Pixel presets (with calculated ratios)
    "1024x1024 (1:1)": (1024, 1024, 1, 1),
    "896x1152 (3:4)": (896, 1152, 3, 4),
    "832x1216 (13:19)": (832, 1216, 13, 19),
    "768x1344 (9:16)": (768, 1344, 9, 16),
    "640x1536 (5:12)": (640, 1536, 5, 12),
    "1152x896 (4:3)": (1152, 896, 4, 3),
    "1216x832 (19:13)": (1216, 832, 19, 13),
    "1344x768 (16:9)": (1344, 768, 16, 9),
    "1536x640 (12:5)": (1536, 640, 12, 5),
    # Model-native presets from sandbox
    "SD15_512x512 (1:1)": (512, 512, 1, 1),
    "SDXL_1024x1024 (1:1)": (1024, 1024, 1, 1),
    "Flux_768x768 (1:1)": (768, 768, 1, 1),
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

        # Cast to AspectRatioPreset for named field access
        preset = AspectRatioPreset(*preset_value)
        return self._validate_preset_tuple(preset_name, preset)

    def _validate_preset_tuple(self, preset_name: str, preset: AspectRatioPreset) -> str | None:
        """Validate the structure and values of a preset tuple."""
        if len(preset) != PRESET_TUPLE_SIZE:
            return f"Preset '{preset_name}' must be a tuple with exactly {PRESET_TUPLE_SIZE} elements."

        # Check for invalid values (zero or negative)
        error = self._validate_preset_values(preset_name, preset)
        if error:
            return error

        # Check for partial specifications
        error = self._validate_preset_completeness(preset_name, preset)
        if error:
            return error

        # Verify math if both pixels and ratio are specified
        if (
            preset.width is not None
            and preset.height is not None
            and preset.aspect_width is not None
            and preset.aspect_height is not None
        ):
            return self._validate_preset_math(
                preset_name, preset.width, preset.height, preset.aspect_width, preset.aspect_height
            )

        return None

    def _validate_preset_values(self, preset_name: str, preset: AspectRatioPreset) -> str | None:
        """Validate that preset values are positive."""
        if preset.width is not None and preset.width <= 0:
            return f"Preset '{preset_name}' has invalid width {preset.width} (must be positive)."
        if preset.height is not None and preset.height <= 0:
            return f"Preset '{preset_name}' has invalid height {preset.height} (must be positive)."
        if preset.aspect_width is not None and preset.aspect_width <= 0:
            return f"Preset '{preset_name}' has invalid aspect width {preset.aspect_width} (must be positive)."
        if preset.aspect_height is not None and preset.aspect_height <= 0:
            return f"Preset '{preset_name}' has invalid aspect height {preset.aspect_height} (must be positive)."
        return None

    def _validate_preset_completeness(self, preset_name: str, preset: AspectRatioPreset) -> str | None:
        """Validate that preset dimensions are complete (both or neither for pixels and ratio)."""
        # Check for partial pixel dimensions
        if (preset.width is None) != (preset.height is None):
            return f"Preset '{preset_name}' has only one pixel dimension specified (need both or neither)."

        # Check for partial ratio dimensions
        if (preset.aspect_width is None) != (preset.aspect_height is None):
            return f"Preset '{preset_name}' has only one aspect ratio dimension specified (need both or neither)."

        # Must have at least pixels OR ratio
        if preset.width is None and preset.aspect_width is None:
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

        # Acquire lock and handle parameter changes
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
                    pass  # Modifiers just need outputs recalculated, which always happens in finally.
        finally:
            # Always recalculate final outputs and release lock
            try:
                self._calculate_outputs()
                # Success - set status
                final_width = self.parameter_output_values[self._final_width_parameter.name]
                final_height = self.parameter_output_values[self._final_height_parameter.name]
                self._set_status_results(was_successful=True, result_details=f"{final_width}x{final_height}")
            except ValueError as e:
                # Handler or validation error - set failure status
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
        elif width < 0:
            errors.append(f"Parameter '{self._width_parameter.name}' must be non-negative (got {width}).")

        if height is None:
            errors.append(f"Parameter '{self._height_parameter.name}' was missing or could not be calculated.")
        elif height < 0:
            errors.append(f"Parameter '{self._height_parameter.name}' must be non-negative (got {height}).")

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

        preset_value = ASPECT_RATIO_PRESETS[preset_name]
        if preset_value is None:
            error_msg = f"Preset '{preset_name}' cannot be applied (only '{CUSTOM_PRESET_NAME}' can be None)."
            raise ValueError(error_msg)

        # Cast to AspectRatioPreset for named field access
        preset = AspectRatioPreset(*preset_value)

        # Case 1: Preset has pixel dimensions specified - use them directly
        if preset.width is not None and preset.height is not None:
            self._apply_pixel_preset(preset.width, preset.height)
        # Case 2: Preset has only ratio specified - calculate pixels from current dimensions
        elif preset.aspect_width is not None and preset.aspect_height is not None:
            self._apply_ratio_preset(preset.aspect_width, preset.aspect_height)

    def _apply_pixel_preset(self, preset_width: int, preset_height: int) -> None:
        """Apply a preset with pixel dimensions specified."""
        # Calculate ratio from pixels first
        ratio = self._calculate_ratio(preset_width, preset_height)
        if ratio is None:
            error_msg = f"Failed to calculate ratio from preset dimensions {preset_width}x{preset_height}."
            raise ValueError(error_msg)

        # Update all parameters
        self.set_parameter_value(self._width_parameter.name, preset_width)
        self.set_parameter_value(self._height_parameter.name, preset_height)

        ratio_str = f"{ratio[0]}:{ratio[1]}"
        self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

        ratio_decimal = ratio[0] / ratio[1]
        self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

    def _apply_ratio_preset(self, preset_aspect_width: int, preset_aspect_height: int) -> None:
        """Apply a preset with only ratio specified - calculate pixels from current dimensions."""
        # Get current dimensions
        current_width = self.get_parameter_value(self._width_parameter.name)
        current_height = self.get_parameter_value(self._height_parameter.name)

        # Determine which dimension is primary based on aspect ratio
        width_is_primary = preset_aspect_width >= preset_aspect_height

        # Calculate new dimensions - swap dimensions and ratio if height is primary
        if width_is_primary:
            new_width, new_height = self._calculate_dimensions_from_primary(
                current_width, current_height, preset_aspect_width, preset_aspect_height
            )
        else:
            # Height is primary - swap everything
            new_height, new_width = self._calculate_dimensions_from_primary(
                current_height, current_width, preset_aspect_height, preset_aspect_width
            )

        # Validate calculated dimensions before updating (negative values are invalid)
        if new_width < 0 or new_height < 0:
            error_msg = (
                f"Failed to calculate valid dimensions from ratio {preset_aspect_width}:{preset_aspect_height}. "
                f"Got {new_width}x{new_height}."
            )
            raise ValueError(error_msg)

        # Update all parameters
        self.set_parameter_value(self._width_parameter.name, new_width)
        self.set_parameter_value(self._height_parameter.name, new_height)

        ratio_str = f"{preset_aspect_width}:{preset_aspect_height}"
        self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

        ratio_decimal = preset_aspect_width / preset_aspect_height
        self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

    def _calculate_dimensions_from_primary(
        self, primary_dimension: int | None, secondary_dimension: int | None, primary_aspect: int, secondary_aspect: int
    ) -> tuple[int, int]:
        """Calculate dimensions using primary dimension and aspect ratio.

        Args:
            primary_dimension: The primary dimension value (e.g., width if width is primary)
            secondary_dimension: The secondary dimension value (e.g., height if width is primary)
            primary_aspect: The primary aspect ratio value (e.g., 4 in 4:3 if width is primary)
            secondary_aspect: The secondary aspect ratio value (e.g., 3 in 4:3 if width is primary)

        Returns:
            Tuple of (primary_result, secondary_result) in the same order as inputs
        """
        has_valid_primary = primary_dimension is not None and primary_dimension >= 0
        has_valid_secondary = secondary_dimension is not None and secondary_dimension >= 0

        # Failure case: Neither dimension available
        if not has_valid_primary and not has_valid_secondary:
            error_msg = "Cannot calculate dimensions: both current width and height are missing or invalid."
            raise ValueError(error_msg)

        # Calculate dimensions based on what's available
        match (has_valid_primary, has_valid_secondary):
            case (True, True):
                # Both dimensions available - use the larger one as the primary
                if primary_dimension is None or secondary_dimension is None:
                    error_msg = "Internal error: dimensions should not be None after validation."
                    raise ValueError(error_msg)
                larger_dimension = max(primary_dimension, secondary_dimension)
                new_primary = larger_dimension
                new_secondary = round(new_primary * secondary_aspect / primary_aspect)
            case (True, False):
                # Only primary dimension available - use it directly
                if primary_dimension is None:
                    error_msg = "Internal error: primary dimension should not be None after validation."
                    raise ValueError(error_msg)
                new_primary = primary_dimension
                new_secondary = round(new_primary * secondary_aspect / primary_aspect)
            case (False, True):
                # Only secondary dimension available - calculate primary from it
                if secondary_dimension is None:
                    error_msg = "Internal error: secondary dimension should not be None after validation."
                    raise ValueError(error_msg)
                new_secondary = secondary_dimension
                new_primary = round(new_secondary * primary_aspect / secondary_aspect)
            case _:
                # This should be unreachable due to early-out above
                error_msg = "Internal error: unreachable case in dimension calculation."
                raise ValueError(error_msg)

        return (new_primary, new_secondary)

    def _handle_width_change(self, width: int) -> None:
        """Handle width parameter changes - update ratio and match preset."""
        height = self.get_parameter_value(self._height_parameter.name)
        self._handle_dimension_change(width, height)

    def _handle_height_change(self, height: int) -> None:
        """Handle height parameter changes - update ratio and match preset."""
        width = self.get_parameter_value(self._width_parameter.name)
        self._handle_dimension_change(width, height)

    def _handle_dimension_change(self, width: int | None, height: int | None) -> None:
        """Handle dimension parameter changes - update ratio and match preset."""
        # Early out for invalid values
        if width is None or height is None or width < 0 or height < 0:
            error_msg = f"Cannot calculate ratio from dimensions {width}x{height}."
            raise ValueError(error_msg)

        # Calculate and validate ratio
        ratio = self._calculate_ratio(width, height)
        if ratio is None:
            error_msg = f"Failed to calculate ratio from dimensions {width}x{height}."
            raise ValueError(error_msg)

        # Update all ratio parameters
        ratio_str = f"{ratio[0]}:{ratio[1]}"
        self.set_parameter_value(self._ratio_str_parameter.name, ratio_str)

        # Calculate ratio decimal (special case for 0:0)
        if ratio[0] == 0 and ratio[1] == 0:
            ratio_decimal = 0.0
        else:
            ratio_decimal = ratio[0] / ratio[1]
        self.set_parameter_value(self._ratio_decimal_parameter.name, ratio_decimal)

        # Match to preset
        self._match_preset()

    def _handle_ratio_str_change(self, ratio_str: str) -> None:
        """Handle ratio_str parameter changes - update decimal and match preset."""
        # Validate input format
        if not ratio_str:
            error_msg = "Ratio string cannot be empty."
            raise ValueError(error_msg)

        if ":" not in ratio_str:
            error_msg = f"Invalid ratio format '{ratio_str}' - expected format 'width:height' (e.g., '16:9')."
            raise ValueError(error_msg)

        # Parse ratio string (expected format: "width:height")
        parts = ratio_str.split(":")
        expected_parts_count = 2
        if len(parts) != expected_parts_count:
            error_msg = (
                f"Invalid ratio format '{ratio_str}' - expected exactly two parts separated by ':' (e.g., '16:9')."
            )
            raise ValueError(error_msg)

        try:
            aspect_width = int(parts[0].strip())
            aspect_height = int(parts[1].strip())
        except ValueError as e:
            error_msg = f"Invalid ratio format '{ratio_str}' - both parts must be integers: {e}."
            raise ValueError(error_msg) from e

        # Validate aspect ratio values (must be non-negative, but if one is 0, both must be 0)
        if aspect_width < 0 or aspect_height < 0:
            error_msg = f"Invalid aspect ratio {aspect_width}:{aspect_height} - values cannot be negative."
            raise ValueError(error_msg)

        # Special case: if either dimension is 0, both must be 0
        if (aspect_width == 0 or aspect_height == 0) and not (aspect_width == 0 and aspect_height == 0):
            error_msg = f"Invalid aspect ratio {aspect_width}:{aspect_height} - if either value is 0, both must be 0."
            raise ValueError(error_msg)

        # Update ratio decimal (special case for 0:0)
        if aspect_width == 0 and aspect_height == 0:
            ratio_decimal = 0.0
        else:
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
        # Special case: 0 dimensions result in 0:0 ratio
        if width == 0 or height == 0:
            return (0, 0)

        # Early out for negative dimensions
        if width < 0 or height < 0:
            return None

        divisor = gcd(width, height)
        ratio_width = width // divisor
        ratio_height = height // divisor

        # Success path
        return (ratio_width, ratio_height)
