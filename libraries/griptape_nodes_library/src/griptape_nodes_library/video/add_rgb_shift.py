from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddRGBShift(BaseVideoProcessor):
    """Add RGB shift (chromatic aberration) effect to video."""

    # RGB shift constants
    MIN_SHIFT = -50
    MAX_SHIFT = 50
    DEFAULT_SHIFT = 6

    # RGB shift intensity constants
    MIN_INTENSITY = 0.0
    MAX_INTENSITY = 1.0
    DEFAULT_INTENSITY = 1.0

    # Tear effect constants
    MIN_TEAR_OFFSET = -50
    MAX_TEAR_OFFSET = 50

    def _setup_custom_parameters(self) -> None:
        """Setup RGB shift-specific parameters."""
        # RGB shift parameters
        with ParameterGroup(name="rgb_shift_settings", ui_options={"collapsed": False}) as rgb_group:
            # Red channel horizontal shift
            Parameter(
                name="red_horizontal",
                type="int",
                default_value=-self.DEFAULT_SHIFT,
                tooltip=f"Red channel horizontal shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Red channel vertical shift
            Parameter(
                name="red_vertical",
                type="int",
                default_value=0,
                tooltip=f"Red channel vertical shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Green channel horizontal shift
            Parameter(
                name="green_horizontal",
                type="int",
                default_value=self.DEFAULT_SHIFT,
                tooltip=f"Green channel horizontal shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Green channel vertical shift
            Parameter(
                name="green_vertical",
                type="int",
                default_value=0,
                tooltip=f"Green channel vertical shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Blue channel horizontal shift
            Parameter(
                name="blue_horizontal",
                type="int",
                default_value=0,
                tooltip=f"Blue channel horizontal shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Blue channel vertical shift
            Parameter(
                name="blue_vertical",
                type="int",
                default_value=0,
                tooltip=f"Blue channel vertical shift ({self.MIN_SHIFT} to {self.MAX_SHIFT} pixels)",
            ).add_trait(Slider(min_val=self.MIN_SHIFT, max_val=self.MAX_SHIFT))

            # Overall intensity
            Parameter(
                name="intensity",
                type="float",
                default_value=self.DEFAULT_INTENSITY,
                tooltip=f"Overall intensity of the RGB shift effect ({self.MIN_INTENSITY}-{self.MAX_INTENSITY})",
            ).add_trait(Slider(min_val=self.MIN_INTENSITY, max_val=self.MAX_INTENSITY))

        self.add_node_element(rgb_group)

        # Tear effect parameters
        with ParameterGroup(name="tear_effect_settings", ui_options={"collapsed": True}) as tear_group:
            Parameter(
                name="tear_enabled",
                type="bool",
                default_value=False,
                tooltip="Enable tear effect",
            )

            Parameter(
                name="tear_position",
                type="float",
                default_value=0.5,
                tooltip="Vertical position of tear (0.0-1.0, where 0.5 is center)",
            ).add_trait(Slider(min_val=0.0, max_val=1.0))

            Parameter(
                name="tear_offset",
                type="int",
                default_value=10,
                tooltip=f"Horizontal offset amount for tear effect ({self.MIN_TEAR_OFFSET} to {self.MAX_TEAR_OFFSET} pixels)",
            ).add_trait(Slider(min_val=self.MIN_TEAR_OFFSET, max_val=self.MAX_TEAR_OFFSET))

        self.add_node_element(tear_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "RGB shift (chromatic aberration) addition"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for RGB shift effect."""
        red_h = kwargs.get("red_horizontal", -self.DEFAULT_SHIFT)
        red_v = kwargs.get("red_vertical", 0)
        green_h = kwargs.get("green_horizontal", self.DEFAULT_SHIFT)
        green_v = kwargs.get("green_vertical", 0)
        blue_h = kwargs.get("blue_horizontal", 0)
        blue_v = kwargs.get("blue_vertical", 0)
        intensity = kwargs.get("intensity", self.DEFAULT_INTENSITY)

        # Tear effect parameters
        tear_enabled = kwargs.get("tear_enabled", False)
        tear_position = kwargs.get("tear_position", 0.5)
        tear_offset = kwargs.get("tear_offset", 10)

        # Apply intensity scaling to all shifts and clamp to FFmpeg's valid range (-255 to 255)
        red_h_scaled = max(-255, min(255, int(red_h * intensity)))
        red_v_scaled = max(-255, min(255, int(red_v * intensity)))
        green_h_scaled = max(-255, min(255, int(green_h * intensity)))
        green_v_scaled = max(-255, min(255, int(green_v * intensity)))
        blue_h_scaled = max(-255, min(255, int(blue_h * intensity)))
        blue_v_scaled = max(-255, min(255, int(blue_v * intensity)))

        if tear_enabled:
            # Create tear effect by splitting the video and applying different RGB shifts
            tear_y = f"ih*{tear_position}"

            custom_filter = (
                f"split=3[main][tear_top][tear_bottom];"
                f"[main]rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}[rgb_shifted];"
                f"[tear_top]crop=iw:{tear_y}:0:0,rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}[top_shifted];"
                f"[tear_bottom]crop=iw:ih-{tear_y}:0:{tear_y},rgbashift=rh={red_h_scaled + tear_offset}:rv={red_v_scaled}:"
                f"gh={green_h_scaled + tear_offset}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled + tear_offset}:bv={blue_v_scaled}[bottom_shifted];"
                f"[top_shifted][bottom_shifted]vstack[tear_effect];"
                f"[rgb_shifted][tear_effect]overlay=0:0[out]"
            )
        else:
            # Simple RGB shift without tear effect
            custom_filter = (
                f"rgbashift=rh={red_h_scaled}:rv={red_v_scaled}:"
                f"gh={green_h_scaled}:gv={green_v_scaled}:"
                f"bh={blue_h_scaled}:bv={blue_v_scaled}"
            )

        # Combine with frame rate filter if needed
        filter_complex = self._combine_video_filters(custom_filter, input_frame_rate)

        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Get ffmpeg executable path
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        return [
            ffmpeg_path,
            "-i",
            input_url,
            "-vf",
            filter_complex,
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            pix_fmt,
            "-movflags",
            "+faststart",
            "-c:a",
            "copy",
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate RGB shift parameters."""
        exceptions = []

        # Validate shift values
        for param_name in [
            "red_horizontal",
            "red_vertical",
            "green_horizontal",
            "green_vertical",
            "blue_horizontal",
            "blue_vertical",
        ]:
            value = self.get_parameter_value(param_name)
            if value is not None and (value < self.MIN_SHIFT or value > self.MAX_SHIFT):
                msg = f"{self.name} - {param_name} must be between {self.MIN_SHIFT} and {self.MAX_SHIFT}, got {value}"
                exceptions.append(ValueError(msg))

        # Validate intensity
        intensity = self.get_parameter_value("intensity")
        if intensity is not None and (intensity < self.MIN_INTENSITY or intensity > self.MAX_INTENSITY):
            msg = f"{self.name} - Intensity must be between {self.MIN_INTENSITY} and {self.MAX_INTENSITY}, got {intensity}"
            exceptions.append(ValueError(msg))

        # Validate tear effect parameters
        tear_position = self.get_parameter_value("tear_position")
        if tear_position is not None and (tear_position < 0.0 or tear_position > 1.0):
            msg = f"{self.name} - Tear position must be between 0.0 and 1.0, got {tear_position}"
            exceptions.append(ValueError(msg))

        tear_offset = self.get_parameter_value("tear_offset")
        if tear_offset is not None and (tear_offset < self.MIN_TEAR_OFFSET or tear_offset > self.MAX_TEAR_OFFSET):
            msg = f"{self.name} - Tear offset must be between {self.MIN_TEAR_OFFSET} and {self.MAX_TEAR_OFFSET}, got {tear_offset}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get RGB shift parameters."""
        return {
            "red_horizontal": self.get_parameter_value("red_horizontal"),
            "red_vertical": self.get_parameter_value("red_vertical"),
            "green_horizontal": self.get_parameter_value("green_horizontal"),
            "green_vertical": self.get_parameter_value("green_vertical"),
            "blue_horizontal": self.get_parameter_value("blue_horizontal"),
            "blue_vertical": self.get_parameter_value("blue_vertical"),
            "intensity": self.get_parameter_value("intensity"),
            "tear_enabled": self.get_parameter_value("tear_enabled"),
            "tear_position": self.get_parameter_value("tear_position"),
            "tear_offset": self.get_parameter_value("tear_offset"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        red_h = kwargs.get("red_horizontal", -self.DEFAULT_SHIFT)
        red_v = kwargs.get("red_vertical", 0)
        green_h = kwargs.get("green_horizontal", self.DEFAULT_SHIFT)
        green_v = kwargs.get("green_vertical", 0)
        blue_h = kwargs.get("blue_horizontal", 0)
        blue_v = kwargs.get("blue_vertical", 0)
        intensity = kwargs.get("intensity", self.DEFAULT_INTENSITY)
        tear_enabled = kwargs.get("tear_enabled", False)

        suffix = f"_rgbshift_rh{red_h}_rv{red_v}_gh{green_h}_gv{green_v}_bh{blue_h}_bv{blue_v}_i{intensity:.2f}"

        if tear_enabled:
            tear_position = kwargs.get("tear_position", 0.5)
            tear_offset = kwargs.get("tear_offset", 10)
            suffix += f"_tear_p{tear_position:.2f}_o{tear_offset}"

        return suffix
