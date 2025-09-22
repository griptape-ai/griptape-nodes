from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class HoldVideoFrames(BaseVideoProcessor):
    """Hold video frames for a specified number of frames, creating a stepped video effect."""

    MAX_HOLD_FRAMES = 10
    MIN_HOLD_FRAMES = 1
    DEFAULT_HOLD_FRAMES = 2

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for frame holding."""
        # Add hold frames parameter
        hold_frames_parameter = Parameter(
            name="hold_frames",
            type="int",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=self.DEFAULT_HOLD_FRAMES,
            tooltip="Number of frames to hold (e.g., 2 = video updates every 2 frames)",
        )
        self.add_parameter(hold_frames_parameter)
        hold_frames_parameter.add_trait(Slider(min_val=self.MIN_HOLD_FRAMES, max_val=self.MAX_HOLD_FRAMES))

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video frame holding"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build the FFmpeg command for frame holding."""
        hold_frames = kwargs.get("hold_frames", 2)

        # Get the original frame rate from the input video
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
        frame_rate, _resolution, _duration = self._detect_video_properties(input_url, ffprobe_path)
        original_fps = frame_rate

        # Create frame holding effect by reducing frame rate and then duplicating frames
        reduced_fps = original_fps / hold_frames
        self.append_value_to_parameter("logs", f"Reduced frame rate for holding: {reduced_fps} fps\n")
        base_filter = f"fps=fps={reduced_fps},fps=fps={original_fps}"

        # Add output frame rate filter if needed (after the hold effect)
        frame_rate_filter = self._get_frame_rate_filter(original_fps)
        if frame_rate_filter:
            base_filter = f"{base_filter},{frame_rate_filter}"

        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Build ffmpeg command using filter with processing speed settings
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_url,
            "-vf",
            base_filter,
            "-c:a",
            "copy",
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
            output_path,
        ]

        return cmd

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters."""
        exceptions = []

        # Validate hold_frames
        hold_frames = self.parameter_values.get("hold_frames", self.DEFAULT_HOLD_FRAMES)
        if hold_frames < self.MIN_HOLD_FRAMES or hold_frames > self.MAX_HOLD_FRAMES:
            msg = f"{self.name}: Hold frames must be between {self.MIN_HOLD_FRAMES} and {self.MAX_HOLD_FRAMES}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {"hold_frames": self.parameter_values.get("hold_frames", self.DEFAULT_HOLD_FRAMES)}

    def _get_output_suffix(self, **kwargs) -> str:
        """Get the output filename suffix."""
        hold_frames = kwargs.get("hold_frames", self.DEFAULT_HOLD_FRAMES)
        return f"_hold_{hold_frames}_frames"
