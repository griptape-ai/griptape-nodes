from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class ChangeSpeed(BaseVideoProcessor):
    """Change the playback speed of a video."""

    # Speed constants
    MIN_SPEED = 0.1
    MAX_SPEED = 10.0
    DEFAULT_SPEED = 1.0

    # Audio filter constants
    ATEMPO_MIN_SPEED = 0.5
    ATEMPO_MAX_SPEED = 2.0

    def _setup_custom_parameters(self) -> None:
        """Setup speed change parameters."""
        with ParameterGroup(name="speed_settings", ui_options={"collapsed": False}) as speed_group:
            # Speed multiplier parameter
            Parameter(
                name="speed",
                type="float",
                default_value=self.DEFAULT_SPEED,
                tooltip=f"Playback speed multiplier ({self.MIN_SPEED}-{self.MAX_SPEED}x, 1.0 = normal speed)",
            ).add_trait(Slider(min_val=self.MIN_SPEED, max_val=self.MAX_SPEED))

            # Include audio parameter
            Parameter(
                name="include_audio",
                type="bool",
                default_value=True,
                tooltip="When enabled, includes audio in the output file. When disabled, creates a silent video.",
            )

        self.add_node_element(speed_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "speed change"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for speed change."""
        speed = kwargs.get("speed", self.DEFAULT_SPEED)
        include_audio = kwargs.get("include_audio", True)

        # Use setpts filter to change video speed
        # PTS (Presentation Time Stamp) controls when each frame is displayed
        # Dividing by speed makes the video play faster/slower
        custom_filter = f"setpts=PTS/{speed}"

        # Combine with frame rate filter if needed
        filter_complex = self._combine_video_filters(custom_filter, input_frame_rate)

        # Get ffmpeg executable path
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        if include_audio:
            # Audio needs to be speed-adjusted to match the video speed change
            # Use atempo filter with speed ratio calculation
            # Note: atempo has limits (0.5x to 2.0x), so we may need to chain multiple filters
            if speed >= self.ATEMPO_MIN_SPEED and speed <= self.ATEMPO_MAX_SPEED:
                audio_filter = f"atempo={speed}"
            else:
                # For extreme speed changes, we'll need to chain atempo filters
                # This is a simplified approach - in practice, you might want more sophisticated handling
                audio_filter = (
                    f"atempo={self.ATEMPO_MAX_SPEED},atempo={self.ATEMPO_MAX_SPEED}"
                    if speed > self.ATEMPO_MAX_SPEED
                    else f"atempo={self.ATEMPO_MIN_SPEED},atempo={self.ATEMPO_MIN_SPEED}"
                )

            # Get processing speed settings
            preset, pix_fmt, crf = self._get_processing_speed_settings()

            # Build the command with audio speed adjustment
            return [
                ffmpeg_path,
                "-i",
                input_url,
                "-vf",
                filter_complex,
                "-af",
                audio_filter,
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
        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()

        # Build the command without audio (silent video)
        return [
            ffmpeg_path,
            "-i",
            input_url,
            "-vf",
            filter_complex,
            "-an",  # No audio
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
            "-y",
            output_path,
        ]

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate speed parameters."""
        exceptions = []

        speed = self.get_parameter_value("speed")
        if speed is not None and (speed < self.MIN_SPEED or speed > self.MAX_SPEED):
            msg = f"{self.name} - Speed must be between {self.MIN_SPEED} and {self.MAX_SPEED}, got {speed}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get speed change parameters."""
        return {
            "speed": self.get_parameter_value("speed"),
            "include_audio": self.get_parameter_value("include_audio"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        speed = kwargs.get("speed", self.DEFAULT_SPEED)
        include_audio = kwargs.get("include_audio", True)

        suffix = f"_speed{speed:.1f}"

        if not include_audio:
            suffix += "_noaudio"

        return suffix
