from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup
from griptape_nodes.traits.options import Options
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class ReverseVideo(BaseVideoProcessor):
    """Reverse video playback."""

    def _setup_custom_parameters(self) -> None:
        """Setup reverse-specific parameters."""
        with ParameterGroup(name="reverse_settings", ui_options={"collapsed": False}) as reverse_group:
            # Audio handling parameter
            audio_parameter = Parameter(
                name="audio_handling",
                type="str",
                default_value="reverse",
                tooltip="How to handle audio: reverse, mute, or keep original",
            )
            self.add_parameter(audio_parameter)
            audio_parameter.add_trait(Options(choices=["reverse", "mute", "keep"]))

        self.add_node_element(reverse_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video reversal"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build FFmpeg command for video reversal."""
        audio_handling = kwargs.get("audio_handling", "reverse")

        # Check if video has audio stream
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
        has_audio = self._detect_audio_stream(input_url, ffprobe_path)

        # Base command
        cmd = [ffmpeg_path, "-i", input_url]

        # Handle video reversal with frame rate consideration
        video_filter = "reverse"

        # Add frame rate filter if needed
        frame_rate_filter = self._get_frame_rate_filter(input_frame_rate)
        if frame_rate_filter:
            video_filter = f"{video_filter},{frame_rate_filter}"

        # Handle audio based on setting and whether audio exists
        if audio_handling == "reverse" and has_audio:
            # Reverse both video and audio (only if audio exists)
            filter_complex = f"[0:v]{video_filter}[v];[0:a]areverse[a]"
            cmd.extend(["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"])
        elif audio_handling == "reverse" and not has_audio:
            # Reverse video only, no audio stream exists
            cmd.extend(["-vf", video_filter, "-an"])
        elif audio_handling == "mute":
            # Reverse video only, no audio
            cmd.extend(["-vf", video_filter, "-an"])
        # Reverse video, keep original audio (only if audio exists)
        elif has_audio:
            cmd.extend(["-vf", video_filter, "-c:a", "copy"])
        else:
            cmd.extend(["-vf", video_filter, "-an"])

        # Add encoding settings
        # Get processing speed settings
        preset, pix_fmt, crf = self._get_processing_speed_settings()
        cmd.extend(
            [
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
        )

        return cmd

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate reverse parameters."""
        exceptions = []

        audio_handling = self.get_parameter_value("audio_handling")
        valid_choices = ["reverse", "mute", "keep"]
        if audio_handling is not None and audio_handling not in valid_choices:
            msg = f"{self.name} - Audio handling must be one of {valid_choices}, got {audio_handling}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, str]:
        """Get reverse parameters."""
        return {
            "audio_handling": self.get_parameter_value("audio_handling"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        audio_handling = kwargs.get("audio_handling", "reverse")
        return f"_reversed_{audio_handling}"
