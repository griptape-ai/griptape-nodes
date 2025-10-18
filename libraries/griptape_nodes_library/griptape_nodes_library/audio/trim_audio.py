import subprocess
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.audio.base_audio_processor import BaseAudioProcessor


class TrimAudio(BaseAudioProcessor):
    """Trim audio to a specific start and end time using FFmpeg."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "Audio"
        self.description = "Trim audio to a specific start and end time"

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for audio trimming."""
        # Start time parameter
        self.add_parameter(
            Parameter(
                name="start_time",
                type="float",
                default_value=0.0,
                tooltip="Start time in seconds (0.0 = beginning of audio)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Start Time (seconds)"},
            )
        )

        # End time parameter
        self.add_parameter(
            Parameter(
                name="end_time",
                type="float",
                default_value=None,
                tooltip="End time in seconds (leave empty to trim to end of audio)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "End Time (seconds)"},
            )
        )

        # Duration parameter (alternative to end_time)
        self.add_parameter(
            Parameter(
                name="duration",
                type="float",
                default_value=None,
                tooltip="Duration in seconds (alternative to end time)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        # Trim mode parameter
        self.add_parameter(
            Parameter(
                name="trim_mode",
                type="str",
                default_value="time",
                tooltip="How to specify the trim range",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "time",
                            "duration",
                        ]
                    )
                },
                ui_options={"display_name": "Trim Mode"},
            )
        )

    def _get_processing_description(self) -> str:
        """Get a description of what this processor does."""
        return "trimming audio"

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters for trimming."""
        exceptions = []

        start_time = self.get_parameter_value("start_time")
        end_time = self.get_parameter_value("end_time")
        duration = self.get_parameter_value("duration")
        trim_mode = self.get_parameter_value("trim_mode") or "time"

        # Validate start time
        if start_time is not None and start_time < 0:
            exceptions.append(ValueError("Start time must be non-negative"))

        # Validate trim mode specific parameters
        if trim_mode == "time":
            if end_time is not None and start_time is not None and end_time <= start_time:
                exceptions.append(ValueError("End time must be greater than start time"))
        elif trim_mode == "duration":
            if duration is not None and duration <= 0:
                exceptions.append(ValueError("Duration must be positive"))
            if duration is None:
                exceptions.append(ValueError("Duration is required when trim mode is 'duration'"))

        return exceptions if exceptions else None

    def _process_audio_with_ffmpeg(self, input_url: str, output_path: str, **kwargs) -> None:  # noqa: ARG002
        """Process the audio using FFmpeg to trim it."""
        start_time = self.get_parameter_value("start_time") or 0.0
        end_time = self.get_parameter_value("end_time")
        duration = self.get_parameter_value("duration")
        trim_mode = self.get_parameter_value("trim_mode") or "time"

        # Build FFmpeg command
        cmd = ["ffmpeg", "-y", "-i", input_url]

        # Add trim parameters based on mode
        if trim_mode == "time" and end_time is not None:
            # Trim from start_time to end_time
            cmd.extend(["-ss", str(start_time), "-to", str(end_time)])
        elif trim_mode == "duration":
            # Trim from start_time for duration seconds
            cmd.extend(["-ss", str(start_time), "-t", str(duration)])
        else:
            # Just trim from start_time to end
            cmd.extend(["-ss", str(start_time)])

        # Add output options based on format
        output_format = self.get_parameter_value("output_format") or "auto"
        if output_format == "auto":
            # Detect from output file extension
            if output_path.endswith(".mp3"):
                cmd.extend(["-c:a", "libmp3lame"])
            elif output_path.endswith(".wav"):
                cmd.extend(["-c:a", "pcm_s16le"])  # WAV with 16-bit PCM
            elif output_path.endswith(".aac"):
                cmd.extend(["-c:a", "aac"])
            elif output_path.endswith(".flac"):
                cmd.extend(["-c:a", "flac"])
            elif output_path.endswith(".ogg"):
                cmd.extend(["-c:a", "libvorbis"])
            else:
                cmd.extend(["-c:a", "libmp3lame"])  # Default to MP3
        # Use format-specific codec
        elif output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame"])
        elif output_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif output_format == "aac":
            cmd.extend(["-c:a", "aac"])
        elif output_format == "flac":
            cmd.extend(["-c:a", "flac"])
        elif output_format == "ogg":
            cmd.extend(["-c:a", "libvorbis"])
        else:
            cmd.extend(["-c:a", "libmp3lame"])  # Default to MP3

        cmd.extend(
            [
                "-avoid_negative_ts",
                "make_zero",  # Handle timestamp issues
                output_path,
            ]
        )

        self.append_value_to_parameter("logs", f"Running FFmpeg command: {' '.join(cmd)}\n")

        try:
            # Run FFmpeg command
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603

            self.append_value_to_parameter("logs", "FFmpeg completed successfully\n")
            if result.stderr:
                self.append_value_to_parameter("logs", f"FFmpeg output: {result.stderr}\n")

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg failed with return code {e.returncode}: {e.stderr}"
            self.append_value_to_parameter("logs", f"Error: {error_msg}\n")
            raise RuntimeError(error_msg) from e
        except FileNotFoundError:
            error_msg = "FFmpeg not found. Please ensure FFmpeg is installed and available in PATH."
            self.append_value_to_parameter("logs", f"Error: {error_msg}\n")
            raise RuntimeError(error_msg) from None

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix for trimmed audio."""
        start_time = self.get_parameter_value("start_time") or 0.0
        end_time = self.get_parameter_value("end_time")
        duration = self.get_parameter_value("duration")
        trim_mode = self.get_parameter_value("trim_mode") or "time"

        if trim_mode == "time" and end_time is not None:
            return f"trimmed_{start_time}s_to_{end_time}s"
        if trim_mode == "duration":
            return f"trimmed_{start_time}s_for_{duration}s"
        return f"trimmed_from_{start_time}s"

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {
            "start_time": self.get_parameter_value("start_time"),
            "end_time": self.get_parameter_value("end_time"),
            "duration": self.get_parameter_value("duration"),
            "trim_mode": self.get_parameter_value("trim_mode"),
        }
