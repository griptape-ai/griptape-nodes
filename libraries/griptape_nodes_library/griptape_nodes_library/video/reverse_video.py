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

    def _build_ffmpeg_command(self, input_url: str, output_path: str, **kwargs) -> list[str]:
        """Build FFmpeg command for video reversal."""
        audio_handling = kwargs.get("audio_handling", "reverse")

        # Base command
        cmd = ["ffmpeg", "-i", input_url]

        # Handle video reversal
        video_filter = "reverse"

        # Handle audio based on setting
        if audio_handling == "reverse":
            # Reverse both video and audio
            filter_complex = "[0:v]reverse[v];[0:a]areverse[a]"
            cmd.extend(["-filter_complex", filter_complex, "-map", "[v]", "-map", "[a]"])
        elif audio_handling == "mute":
            # Reverse video only, no audio
            cmd.extend(["-vf", video_filter, "-an"])
        else:  # "keep"
            # Reverse video, keep original audio (not recommended but possible)
            cmd.extend(["-vf", video_filter, "-c:a", "copy"])

        # Add encoding settings
        cmd.extend(["-c:v", "libx264", "-preset", "veryslow", "-crf", "12", "-y", output_path])

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
