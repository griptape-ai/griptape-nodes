from typing import Any

from griptape.artifacts import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class MergeVideoAudio(BaseVideoProcessor):
    """Merge video and audio files with optional fade in/out effects."""

    # Fade duration constants (in seconds)
    MIN_FADE_DURATION = 0.0
    MAX_FADE_DURATION = 10.0
    DEFAULT_FADE_DURATION = 0.0

    # Audio volume constants
    MIN_VOLUME = 0.0
    MAX_VOLUME = 2.0
    DEFAULT_VOLUME = 1.0

    def _setup_logging_group(self) -> None:
        """Setup the common logging parameter group."""
        with ParameterGroup(name="Logs") as logs_group:
            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default
        self.add_node_element(logs_group)

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for video/audio merging."""
        # Add audio input parameter
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["AudioArtifact", "AudioUrlArtifact"],
                type="AudioUrlArtifact",
                tooltip="The audio to merge with the video",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Audio Input",
                },
            )
        )

        with ParameterGroup(name="merge_settings", ui_options={"collapsed": False}) as merge_group:
            # Audio volume parameter
            volume_parameter = Parameter(
                name="audio_volume",
                type="float",
                default_value=self.DEFAULT_VOLUME,
                tooltip=f"Audio volume multiplier ({self.MIN_VOLUME}-{self.MAX_VOLUME})",
            )
            self.add_parameter(volume_parameter)
            volume_parameter.add_trait(Slider(min_val=self.MIN_VOLUME, max_val=self.MAX_VOLUME))

            # Fade in duration parameter
            fade_in_parameter = Parameter(
                name="fade_in_duration",
                type="float",
                default_value=self.DEFAULT_FADE_DURATION,
                tooltip=f"Fade in duration in seconds ({self.MIN_FADE_DURATION}-{self.MAX_FADE_DURATION})",
            )
            self.add_parameter(fade_in_parameter)
            fade_in_parameter.add_trait(Slider(min_val=self.MIN_FADE_DURATION, max_val=self.MAX_FADE_DURATION))

            # Fade out duration parameter
            fade_out_parameter = Parameter(
                name="fade_out_duration",
                type="float",
                default_value=self.DEFAULT_FADE_DURATION,
                tooltip=f"Fade out duration in seconds ({self.MIN_FADE_DURATION}-{self.MAX_FADE_DURATION})",
            )
            self.add_parameter(fade_out_parameter)
            fade_out_parameter.add_trait(Slider(min_val=self.MIN_FADE_DURATION, max_val=self.MAX_FADE_DURATION))

            # Audio replacement mode parameter
            replace_audio_param = Parameter(
                name="replace_audio",
                type="bool",
                default_value=True,
                tooltip="Replace existing audio in video (True) or mix with existing audio (False)",
            )
            self.add_parameter(replace_audio_param)

        self.add_node_element(merge_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video and audio merging"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build FFmpeg command for video/audio merging."""
        # Get FFmpeg paths from base class
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

        # Get parameters
        audio_url = kwargs.get("audio_url", "")
        audio_volume = kwargs.get("audio_volume", self.DEFAULT_VOLUME)
        fade_in_duration = kwargs.get("fade_in_duration", self.DEFAULT_FADE_DURATION)
        fade_out_duration = kwargs.get("fade_out_duration", self.DEFAULT_FADE_DURATION)
        replace_audio = kwargs.get("replace_audio", True)

        if not audio_url:
            error_msg = "audio_url is required for merging"
            raise ValueError(error_msg)

        # Build the base FFmpeg command
        cmd = [ffmpeg_path, "-i", input_url, "-i", audio_url]

        # Build audio filter complex
        audio_filters = []

        # Add volume adjustment
        if audio_volume != 1.0:
            audio_filters.append(f"volume={audio_volume}")

        # Get video duration once for both fade effects and audio cutting
        _, _, video_duration = self._detect_video_properties(input_url, ffprobe_path)

        # Add fade effects
        if fade_in_duration > 0 or fade_out_duration > 0:
            fade_filter = self._build_fade_filter(fade_in_duration, fade_out_duration, video_duration)
            if fade_filter:
                audio_filters.append(fade_filter)

        # Combine audio filters
        if audio_filters:
            audio_filter_complex = ",".join(audio_filters)
            cmd.extend(["-af", audio_filter_complex])

        # Cut audio to video duration to prevent audio from being longer than video
        if video_duration > 0:
            cmd.extend(["-t", str(video_duration)])

        # Set audio codec and mixing behavior
        if replace_audio:
            # Replace existing audio
            cmd.extend(["-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0"])
        else:
            # Mix with existing audio
            cmd.extend(
                ["-c:a", "aac", "-filter_complex", "[0:a][1:a]amix=inputs=2[aout]", "-map", "0:v:0", "-map", "[aout]"]
            )

        # Add video codec and processing settings
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

    def _build_fade_filter(
        self, fade_in_duration: float, fade_out_duration: float, audio_duration: float | None = None
    ) -> str:
        """Build fade filter string for audio."""
        fade_parts = []

        if fade_in_duration > 0:
            fade_parts.append(f"afade=t=in:d={fade_in_duration}")

        if fade_out_duration > 0:
            if audio_duration and audio_duration > fade_out_duration:
                # Calculate start time for fade out: audio_duration - fade_out_duration
                fade_out_start = audio_duration - fade_out_duration
                fade_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out_duration}")
            else:
                # If we don't have audio duration or it's too short, skip fade out
                # This prevents invalid start times
                pass

        return ",".join(fade_parts) if fade_parts else ""

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate inputs before processing."""
        exceptions = []

        # Validate video input
        video = self.parameter_values.get("video")
        if not video:
            exceptions.append(ValueError(f"{self.name}: Video parameter is required"))
        elif not isinstance(video, VideoUrlArtifact):
            exceptions.append(ValueError(f"{self.name}: Video parameter must be a VideoUrlArtifact"))
        elif hasattr(video, "value") and not video.value:
            exceptions.append(ValueError(f"{self.name}: Video parameter must have a value"))

        # Validate audio input
        audio = self.parameter_values.get("audio")
        if not audio:
            exceptions.append(ValueError(f"{self.name}: Audio parameter is required"))
        elif not isinstance(audio, AudioUrlArtifact):
            exceptions.append(ValueError(f"{self.name}: Audio parameter must be an AudioUrlArtifact"))
        elif hasattr(audio, "value") and not audio.value:
            exceptions.append(ValueError(f"{self.name}: Audio parameter must have a value"))

        # Add custom parameter validation
        custom_exceptions = self._validate_custom_parameters()
        if custom_exceptions:
            exceptions.extend(custom_exceptions)

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters."""
        exceptions = []

        # Validate audio volume
        audio_volume = self.get_parameter_value("audio_volume")
        if audio_volume is not None and (audio_volume < self.MIN_VOLUME or audio_volume > self.MAX_VOLUME):
            msg = f"{self.name} - Audio volume must be between {self.MIN_VOLUME} and {self.MAX_VOLUME}, got {audio_volume}"
            exceptions.append(ValueError(msg))

        # Validate fade durations
        fade_in_duration = self.get_parameter_value("fade_in_duration")
        if fade_in_duration is not None and (
            fade_in_duration < self.MIN_FADE_DURATION or fade_in_duration > self.MAX_FADE_DURATION
        ):
            msg = f"{self.name} - Fade in duration must be between {self.MIN_FADE_DURATION} and {self.MAX_FADE_DURATION}, got {fade_in_duration}"
            exceptions.append(ValueError(msg))

        fade_out_duration = self.get_parameter_value("fade_out_duration")
        if fade_out_duration is not None and (
            fade_out_duration < self.MIN_FADE_DURATION or fade_out_duration > self.MAX_FADE_DURATION
        ):
            msg = f"{self.name} - Fade out duration must be between {self.MIN_FADE_DURATION} and {self.MAX_FADE_DURATION}, got {fade_out_duration}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        # Get audio URL from audio parameter
        audio = self.parameter_values.get("audio")
        audio_url = ""
        if isinstance(audio, AudioUrlArtifact) and hasattr(audio, "value"):
            audio_url = audio.value

        return {
            "audio_url": audio_url,
            "audio_volume": self.get_parameter_value("audio_volume"),
            "fade_in_duration": self.get_parameter_value("fade_in_duration"),
            "fade_out_duration": self.get_parameter_value("fade_out_duration"),
            "replace_audio": self.get_parameter_value("replace_audio"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        audio_volume = kwargs.get("audio_volume", self.DEFAULT_VOLUME)
        fade_in = kwargs.get("fade_in_duration", self.DEFAULT_FADE_DURATION)
        fade_out = kwargs.get("fade_out_duration", self.DEFAULT_FADE_DURATION)
        replace_audio = kwargs.get("replace_audio", True)

        suffix_parts = []
        if audio_volume != 1.0:
            suffix_parts.append(f"vol{audio_volume:.2f}")
        if fade_in > 0:
            suffix_parts.append(f"fadein{fade_in:.1f}")
        if fade_out > 0:
            suffix_parts.append(f"fadeout{fade_out:.1f}")
        if not replace_audio:
            suffix_parts.append("mixed")

        return f"_merged_{'_'.join(suffix_parts)}" if suffix_parts else "_merged"

    def process(self) -> None:
        """Merge video and audio and save as VideoUrlArtifact."""
        # Reset execution state and result details at the start of each run
        self._clear_execution_status()

        # Clear output values to prevent downstream nodes from getting stale data on errors
        self.parameter_output_values["output"] = None

        # Get video input data
        input_url, detected_format = self._get_video_input_data()
        self._log_format_detection(detected_format)

        # Get custom parameters
        custom_params = self._get_custom_parameters()

        # Initialize logs
        self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

        try:
            # Run the video processing
            self.append_value_to_parameter("logs", "[Started video/audio merging..]\n")
            self._process(input_url, detected_format, **custom_params)
            self.append_value_to_parameter("logs", "[Finished video/audio merging.]\n")

            # Success case
            success_details = f"Successfully merged video and audio: {self._get_processing_description()}"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"{self.__class__.__name__} '{self.name}': {success_details}")

        except Exception as e:
            error_details = f"Failed to merge video and audio: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.__class__.__name__} '{self.name}': {error_details}")
            self._handle_failure_exception(e)
