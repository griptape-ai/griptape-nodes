from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class AddColorCurves(BaseVideoProcessor):
    """Add color curves (color grading) effect to video using FFmpeg's curves filter."""

    # Available curve presets (from FFmpeg curves filter)
    CURVE_PRESETS: ClassVar[list[str]] = [
        "none",
        "color_negative",
        "cross_process",
        "darker",
        "increase_contrast",
        "lighter",
        "linear_contrast",
        "medium_contrast",
        "negative",
        "strong_contrast",
        "vintage",
    ]

    def _setup_custom_parameters(self) -> None:
        """Setup color curves parameters."""
        parameter = Parameter(
            name="curve_preset",
            type="str",
            default_value="none",
            tooltip="Built-in curve preset for color grading effects",
        )
        parameter.add_trait(Options(choices=self.CURVE_PRESETS))
        self.add_parameter(parameter)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "color curves"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for color curves."""
        curve_preset = kwargs.get("curve_preset", "none")

        # Build curves filter
        if curve_preset != "none":
            custom_filter = f"curves=preset={curve_preset}"
        else:
            # No curves applied
            custom_filter = "null"

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
            "aac",
            "-b:a",
            "192k",
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate color curves parameters."""
        exceptions = []

        curve_preset = self.get_parameter_value("curve_preset")
        if curve_preset is not None and curve_preset not in self.CURVE_PRESETS:
            msg = f"{self.name} - Curve preset must be one of the available presets, got {curve_preset}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get color curves parameters."""
        return {
            "curve_preset": self.get_parameter_value("curve_preset"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        curve_preset = kwargs.get("curve_preset", "none")

        if curve_preset != "none":
            return f"_curves_{curve_preset}"
        return ""
