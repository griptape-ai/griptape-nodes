import math
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddVignette(BaseVideoProcessor):
    """Add a vignette effect to video."""

    # Vignette angle constants (lens angle) - this controls intensity
    MIN_ANGLE = 0.1
    MAX_ANGLE = math.pi
    DEFAULT_ANGLE = math.pi / 5

    # Vignette center position constants
    MIN_CENTER_OFFSET = -1.0
    MAX_CENTER_OFFSET = 1.0
    DEFAULT_CENTER_OFFSET = 0.0

    # Vignette aspect ratio constants
    MIN_ASPECT = 0.1
    MAX_ASPECT = 10.0
    DEFAULT_ASPECT = 1.0

    def _setup_custom_parameters(self) -> None:
        """Setup vignette-specific parameters."""
        with ParameterGroup(name="vignette_settings", ui_options={"collapsed": False}) as vignette_group:
            # Vignette angle parameter (lens angle) - controls intensity
            angle_parameter = Parameter(
                name="angle",
                type="float",
                default_value=self.DEFAULT_ANGLE,
                tooltip=f"Lens angle for vignette effect - smaller values = stronger effect ({self.MIN_ANGLE}-{self.MAX_ANGLE})",
            )
            self.add_parameter(angle_parameter)
            angle_parameter.add_trait(Slider(min_val=self.MIN_ANGLE, max_val=self.MAX_ANGLE))

            # Vignette center X offset parameter
            center_x_parameter = Parameter(
                name="center_x",
                type="float",
                default_value=self.DEFAULT_CENTER_OFFSET,
                tooltip="Center X offset (-1.0 to 1.0, 0 = center)",
            )
            self.add_parameter(center_x_parameter)
            center_x_parameter.add_trait(Slider(min_val=self.MIN_CENTER_OFFSET, max_val=self.MAX_CENTER_OFFSET))

            # Vignette center Y offset parameter
            center_y_parameter = Parameter(
                name="center_y",
                type="float",
                default_value=self.DEFAULT_CENTER_OFFSET,
                tooltip="Center Y offset (-1.0 to 1.0, 0 = center)",
            )
            self.add_parameter(center_y_parameter)
            center_y_parameter.add_trait(Slider(min_val=self.MIN_CENTER_OFFSET, max_val=self.MAX_CENTER_OFFSET))

            # Vignette aspect ratio parameter
            aspect_parameter = Parameter(
                name="aspect",
                type="float",
                default_value=self.DEFAULT_ASPECT,
                tooltip=f"Aspect ratio of vignette ({self.MIN_ASPECT}-{self.MAX_ASPECT})",
            )
            self.add_parameter(aspect_parameter)
            aspect_parameter.add_trait(Slider(min_val=self.MIN_ASPECT, max_val=self.MAX_ASPECT))

            # Vignette mode parameter
            mode_parameter = Parameter(
                name="mode",
                type="str",
                default_value="forward",
                tooltip="Vignette mode: forward (darken edges) or backward (lighten edges)",
            )
            self.add_parameter(mode_parameter)
            mode_parameter.add_trait(Options(choices=["forward", "backward"]))

        self.add_node_element(vignette_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "vignette effect addition"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for vignette effect."""
        angle = kwargs.get("angle", self.DEFAULT_ANGLE)
        center_x = kwargs.get("center_x", self.DEFAULT_CENTER_OFFSET)
        center_y = kwargs.get("center_y", self.DEFAULT_CENTER_OFFSET)
        aspect = kwargs.get("aspect", self.DEFAULT_ASPECT)
        mode = kwargs.get("mode", "forward")

        # Calculate center position based on offset
        if center_x == 0:
            x0 = "w/2"
        elif center_x > 0:
            x0 = f"w/2+{center_x}*w/2"
        else:
            x0 = f"w/2{center_x}*w/2"  # center_x is negative, so this becomes w/2-0.01*w/2

        if center_y == 0:
            y0 = "h/2"
        elif center_y > 0:
            y0 = f"h/2+{center_y}*h/2"
        else:
            y0 = f"h/2{center_y}*h/2"  # center_y is negative, so this becomes h/2-0.01*h/2

        # Determine mode value
        mode_value = "1" if mode == "backward" else "0"

        # Build vignette filter with all parameters
        custom_filter = f"vignette=angle={angle}:x0={x0}:y0={y0}:aspect={aspect}:mode={mode_value}:dither=false"

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
        """Validate vignette parameters."""
        exceptions = []

        angle = self.get_parameter_value("angle")
        if angle is not None and (angle < self.MIN_ANGLE or angle > self.MAX_ANGLE):
            msg = f"{self.name} - Angle must be between {self.MIN_ANGLE} and {self.MAX_ANGLE}, got {angle}"
            exceptions.append(ValueError(msg))

        center_x = self.get_parameter_value("center_x")
        if center_x is not None and (center_x < self.MIN_CENTER_OFFSET or center_x > self.MAX_CENTER_OFFSET):
            msg = f"{self.name} - Center X must be between {self.MIN_CENTER_OFFSET} and {self.MAX_CENTER_OFFSET}, got {center_x}"
            exceptions.append(ValueError(msg))

        center_y = self.get_parameter_value("center_y")
        if center_y is not None and (center_y < self.MIN_CENTER_OFFSET or center_y > self.MAX_CENTER_OFFSET):
            msg = f"{self.name} - Center Y must be between {self.MIN_CENTER_OFFSET} and {self.MAX_CENTER_OFFSET}, got {center_y}"
            exceptions.append(ValueError(msg))

        aspect = self.get_parameter_value("aspect")
        if aspect is not None and (aspect < self.MIN_ASPECT or aspect > self.MAX_ASPECT):
            msg = f"{self.name} - Aspect must be between {self.MIN_ASPECT} and {self.MAX_ASPECT}, got {aspect}"
            exceptions.append(ValueError(msg))

        mode = self.get_parameter_value("mode")
        valid_modes = ["forward", "backward"]
        if mode is not None and mode not in valid_modes:
            msg = f"{self.name} - Mode must be one of {valid_modes}, got {mode}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get vignette parameters."""
        return {
            "angle": self.get_parameter_value("angle"),
            "center_x": self.get_parameter_value("center_x"),
            "center_y": self.get_parameter_value("center_y"),
            "aspect": self.get_parameter_value("aspect"),
            "mode": self.get_parameter_value("mode"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        angle = kwargs.get("angle", self.DEFAULT_ANGLE)
        center_x = kwargs.get("center_x", self.DEFAULT_CENTER_OFFSET)
        center_y = kwargs.get("center_y", self.DEFAULT_CENTER_OFFSET)
        aspect = kwargs.get("aspect", self.DEFAULT_ASPECT)
        mode = kwargs.get("mode", "forward")

        return f"_vignette_a{angle:.2f}_x{center_x:.2f}_y{center_y:.2f}_r{aspect:.2f}_{mode}"
