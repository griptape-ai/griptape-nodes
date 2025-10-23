import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import static_ffmpeg.run  # type: ignore[import-untyped]
from griptape.artifacts import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact
from griptape_nodes_library.utils.audio_utils import (
    detect_audio_format,
    to_audio_artifact,
)
from griptape_nodes_library.utils.audio_utils import (
    validate_url as validate_audio_url,
)
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.video_utils import detect_video_format, to_video_artifact, validate_url


@dataclass
class AudioFilterConfig:
    """Configuration for building audio filter chains."""

    audio_duration: float
    video_duration: float
    loop_audio: bool
    audio_start_time: float
    loop_phase_offset: float
    audio_volume: float
    fade_type: str
    fade_in_duration: float
    fade_out_duration: float


class AddAudioToVideo(ControlNode):
    """Add an audio track to a video with volume control, looping, and fade effects."""

    # Volume constants
    MIN_VOLUME: ClassVar[float] = 0.0
    MAX_VOLUME: ClassVar[float] = 200.0
    DEFAULT_VOLUME: ClassVar[float] = 100.0

    # Fade type options
    FADE_OPTIONS: ClassVar[list[str]] = ["none", "in", "out", "in_out"]
    DEFAULT_FADE_TYPE = "none"

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Video input
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="The video to add audio to",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Video or Path to Video",
                },
            )
        )

        # Audio input
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["AudioArtifact", "AudioUrlArtifact"],
                type="AudioUrlArtifact",
                tooltip="The audio to add to the video",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Audio or Path to Audio",
                },
            )
        )

        # Audio settings group
        with ParameterGroup(name="audio_settings", ui_options={"collapsed": False}) as audio_group:
            # Loop audio parameter
            loop_param = Parameter(
                name="loop_audio",
                type="bool",
                default_value=False,
                tooltip="If enabled, the audio will loop for the duration of the video. If disabled, it will play once.",
            )
            self.add_parameter(loop_param)

            # Audio start time
            start_time_param = Parameter(
                name="audio_start_time",
                type="float",
                default_value=0.0,
                tooltip="Start time of the audio in seconds (offset from video start)",
            )
            start_time_param.add_trait(Slider(min_val=0.0, max_val=3600.0))
            self.add_parameter(start_time_param)

            # Loop phase offset (only used when looping)
            phase_param = Parameter(
                name="loop_phase_offset",
                type="float",
                default_value=0.0,
                tooltip="Phase offset for looped audio in seconds. Only applies when loop_audio is enabled.",
            )
            phase_param.add_trait(Slider(min_val=0.0, max_val=60.0))
            self.add_parameter(phase_param)

        self.add_node_element(audio_group)

        # Volume settings group
        with ParameterGroup(name="volume_settings", ui_options={"collapsed": False}) as volume_group:
            # Video volume
            video_volume_param = Parameter(
                name="video_volume",
                type="float",
                default_value=self.DEFAULT_VOLUME,
                tooltip="Volume of the original video audio as a percentage (100% = original volume)",
            )
            video_volume_param.add_trait(Slider(min_val=self.MIN_VOLUME, max_val=self.MAX_VOLUME))
            self.add_parameter(video_volume_param)

            # Added audio volume
            audio_volume_param = Parameter(
                name="audio_volume",
                type="float",
                default_value=self.DEFAULT_VOLUME,
                tooltip="Volume of the added audio as a percentage (100% = original volume)",
            )
            audio_volume_param.add_trait(Slider(min_val=self.MIN_VOLUME, max_val=self.MAX_VOLUME))
            self.add_parameter(audio_volume_param)

        self.add_node_element(volume_group)

        # Fade settings group
        with ParameterGroup(name="fade_settings", ui_options={"collapsed": True}) as fade_group:
            # Fade type
            fade_type_param = Parameter(
                name="fade_type",
                type="str",
                default_value=self.DEFAULT_FADE_TYPE,
                tooltip="Fade effect for the added audio: none, fade in, fade out, or both",
            )
            fade_type_param.add_trait(Options(choices=self.FADE_OPTIONS))
            self.add_parameter(fade_type_param)

            # Fade in duration
            fade_in_param = Parameter(
                name="fade_in_duration",
                type="float",
                default_value=1.0,
                tooltip="Duration of fade in effect in seconds (only applies if fade type includes 'in')",
            )
            fade_in_param.add_trait(Slider(min_val=0.0, max_val=10.0))
            self.add_parameter(fade_in_param)

            # Fade out duration
            fade_out_param = Parameter(
                name="fade_out_duration",
                type="float",
                default_value=1.0,
                tooltip="Duration of fade out effect in seconds (only applies if fade type includes 'out')",
            )
            fade_out_param.add_trait(Slider(min_val=0.0, max_val=10.0))
            self.add_parameter(fade_out_param)

        self.add_node_element(fade_group)

        # Output
        self.add_parameter(
            Parameter(
                name="output",
                output_type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The video with added audio",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        # Logging
        self._setup_logging_group()

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
        logs_group.ui_options = {"hide": True}
        self.add_node_element(logs_group)

    def _get_ffmpeg_paths(self) -> tuple[str, str]:
        """Get FFmpeg and FFprobe executable paths."""
        try:
            ffmpeg_path, ffprobe_path = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
            return ffmpeg_path, ffprobe_path  # noqa: TRY300
        except Exception as e:
            error_msg = f"FFmpeg not found. Please ensure static-ffmpeg is properly installed. Error: {e!s}"
            raise ValueError(error_msg) from e

    def _detect_video_duration(self, input_url: str, ffprobe_path: str) -> float:
        """Detect video duration in seconds."""
        try:
            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "v:0",
                input_url,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)  # noqa: S603
            import json

            streams_data = json.loads(result.stdout)

            if streams_data.get("streams") and len(streams_data["streams"]) > 0:
                video_stream = streams_data["streams"][0]
                duration_str = video_stream.get("duration", "0")
                return float(duration_str) if duration_str != "N/A" else 0.0

            return 0.0  # noqa: TRY300

        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Could not detect video duration, using 0: {e}\n")
            return 0.0

    def _detect_audio_stream(self, input_url: str, ffprobe_path: str) -> bool:
        """Detect if the video has an audio stream."""
        try:
            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                input_url,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)  # noqa: S603
            return "audio" in result.stdout.strip()
        except Exception:
            return False

    def _detect_audio_duration(self, input_url: str, ffprobe_path: str) -> float:
        """Detect audio duration in seconds."""
        try:
            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "a:0",
                input_url,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)  # noqa: S603
            import json

            streams_data = json.loads(result.stdout)

            if streams_data.get("streams") and len(streams_data["streams"]) > 0:
                audio_stream = streams_data["streams"][0]
                duration_str = audio_stream.get("duration", "0")
                return float(duration_str) if duration_str != "N/A" else 0.0

            return 0.0  # noqa: TRY300

        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Could not detect audio duration, using 0: {e}\n")
            return 0.0

    def _validate_url_safety(self, url: str) -> None:
        """Validate that the URL is safe for ffmpeg processing."""
        if not validate_url(url):
            msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
            raise ValueError(msg)

    def _validate_audio_url_safety(self, url: str) -> None:
        """Validate that the audio URL is safe for ffmpeg processing."""
        if not validate_audio_url(url):
            msg = f"{self.name}: Invalid or unsafe audio URL provided: {url}"
            raise ValueError(msg)

    def _validate_video_input(self) -> list[Exception]:
        """Validate video input parameter."""
        exceptions = []
        video = self.parameter_values.get("video")

        if not video:
            exceptions.append(ValueError(f"{self.name}: Video parameter is required"))
            return exceptions

        if not isinstance(video, VideoUrlArtifact):
            exceptions.append(ValueError(f"{self.name}: Video parameter must be a VideoUrlArtifact"))
            return exceptions

        if hasattr(video, "value") and not video.value:  # type: ignore  # noqa: PGH003
            exceptions.append(ValueError(f"{self.name}: Video parameter must have a value"))

        return exceptions

    def _validate_audio_input(self) -> list[Exception]:
        """Validate audio input parameter."""
        exceptions = []
        audio = self.parameter_values.get("audio")

        if not audio:
            exceptions.append(ValueError(f"{self.name}: Audio parameter is required"))
            return exceptions

        if not isinstance(audio, AudioUrlArtifact):
            exceptions.append(ValueError(f"{self.name}: Audio parameter must be an AudioUrlArtifact"))
            return exceptions

        if hasattr(audio, "value") and not audio.value:  # type: ignore  # noqa: PGH003
            exceptions.append(ValueError(f"{self.name}: Audio parameter must have a value"))

        return exceptions

    def _validate_volume_parameters(self) -> list[Exception]:
        """Validate volume parameters."""
        exceptions = []

        video_volume = self.get_parameter_value("video_volume")
        if video_volume is not None and (video_volume < self.MIN_VOLUME or video_volume > self.MAX_VOLUME):
            msg = (
                f"{self.name}: Video volume must be between {self.MIN_VOLUME} and {self.MAX_VOLUME}, got {video_volume}"
            )
            exceptions.append(ValueError(msg))

        audio_volume = self.get_parameter_value("audio_volume")
        if audio_volume is not None and (audio_volume < self.MIN_VOLUME or audio_volume > self.MAX_VOLUME):
            msg = (
                f"{self.name}: Audio volume must be between {self.MIN_VOLUME} and {self.MAX_VOLUME}, got {audio_volume}"
            )
            exceptions.append(ValueError(msg))

        return exceptions

    def _validate_timing_and_fade_parameters(self) -> list[Exception]:
        """Validate timing and fade parameters."""
        exceptions = []

        audio_start_time = self.get_parameter_value("audio_start_time")
        if audio_start_time is not None and audio_start_time < 0:
            exceptions.append(ValueError(f"{self.name}: Audio start time must be >= 0, got {audio_start_time}"))

        loop_phase_offset = self.get_parameter_value("loop_phase_offset")
        if loop_phase_offset is not None and loop_phase_offset < 0:
            exceptions.append(ValueError(f"{self.name}: Loop phase offset must be >= 0, got {loop_phase_offset}"))

        fade_in_duration = self.get_parameter_value("fade_in_duration")
        if fade_in_duration is not None and fade_in_duration < 0:
            exceptions.append(ValueError(f"{self.name}: Fade in duration must be >= 0, got {fade_in_duration}"))

        fade_out_duration = self.get_parameter_value("fade_out_duration")
        if fade_out_duration is not None and fade_out_duration < 0:
            exceptions.append(ValueError(f"{self.name}: Fade out duration must be >= 0, got {fade_out_duration}"))

        fade_type = self.get_parameter_value("fade_type")
        if fade_type and fade_type not in self.FADE_OPTIONS:
            exceptions.append(ValueError(f"{self.name}: Fade type must be one of {self.FADE_OPTIONS}, got {fade_type}"))

        return exceptions

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate inputs and parameters before processing."""
        exceptions = []

        exceptions.extend(self._validate_video_input())
        exceptions.extend(self._validate_audio_input())
        exceptions.extend(self._validate_volume_parameters())
        exceptions.extend(self._validate_timing_and_fade_parameters())

        return exceptions if exceptions else None

    def _build_audio_filter(self, config: AudioFilterConfig) -> str:
        """Build the audio filter chain for the added audio."""
        filters = []

        # Apply looping if needed
        if config.loop_audio and config.video_duration > 0:
            # Calculate how many loops we need
            # -1 means infinite loop, but we'll limit to video duration
            filters.append("aloop=loop=-1:size=2e+09")

            # Apply phase offset if specified
            if config.loop_phase_offset > 0:
                # Adelay takes milliseconds
                delay_ms = int(config.loop_phase_offset * 1000)
                filters.append(f"adelay={delay_ms}|{delay_ms}")

        # Apply start time offset if specified
        if config.audio_start_time > 0:
            delay_ms = int(config.audio_start_time * 1000)
            filters.append(f"adelay={delay_ms}|{delay_ms}")

        # Apply volume adjustment
        volume_multiplier = config.audio_volume / 100.0
        filters.append(f"volume={volume_multiplier}")

        # Apply fade effects
        if config.fade_type in {"in", "in_out"}:
            # Fade in from the start of the audio (after delays)
            filters.append(f"afade=t=in:st=0:d={config.fade_in_duration}")

        if config.fade_type in {"out", "in_out"}:
            # For fade out, we need to calculate when to start the fade
            # If looping, fade out at the end of the video
            if config.loop_audio and config.video_duration > 0:
                fade_start = max(0, config.video_duration - config.fade_out_duration)
                filters.append(f"afade=t=out:st={fade_start}:d={config.fade_out_duration}")
            else:
                # If not looping, fade out at the end of the audio
                fade_start = max(0, config.audio_duration - config.fade_out_duration)
                filters.append(f"afade=t=out:st={fade_start}:d={config.fade_out_duration}")

        # Limit duration to video duration if looping
        if config.loop_audio and config.video_duration > 0:
            filters.append(f"atrim=0:{config.video_duration}")

        return ",".join(filters) if filters else "anull"

    def _build_ffmpeg_command(
        self,
        video_url: str,
        audio_url: str,
        output_path: str,
        filter_config: AudioFilterConfig,
        *,
        has_video_audio: bool,
    ) -> list[str]:
        """Build the FFmpeg command for adding audio to video."""
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        # Get video volume parameter
        video_volume = self.get_parameter_value("video_volume") or self.DEFAULT_VOLUME

        # Build the command
        cmd = [
            ffmpeg_path,
            "-i",
            video_url,  # Input 0: video
            "-i",
            audio_url,  # Input 1: audio to add
        ]

        # Build audio filter chain
        audio_filter = self._build_audio_filter(filter_config)

        # Build the complete filter graph
        if has_video_audio:
            # Mix original video audio with new audio
            video_volume_multiplier = video_volume / 100.0
            filter_complex = f"[0:a]volume={video_volume_multiplier}[a0];[1:a]{audio_filter}[a1];[a0][a1]amix=inputs=2:duration=longest[aout]"
            cmd.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]"])
        else:
            # Just add the new audio to the video
            filter_complex = f"[1:a]{audio_filter}[aout]"
            cmd.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]"])

        # Codec settings
        cmd.extend(
            [
                "-c:v",
                "copy",  # Copy video stream without re-encoding
                "-c:a",
                "aac",  # Encode audio as AAC
                "-b:a",
                "192k",  # Audio bitrate
                "-shortest",  # End when shortest stream ends (video duration)
                "-y",  # Overwrite output file
                output_path,
            ]
        )

        return cmd

    def _save_video_artifact(self, video_bytes: bytes, format_extension: str) -> VideoUrlArtifact:
        """Save video bytes to static file and return VideoUrlArtifact."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Generate meaningful filename
        filename = generate_filename(
            node_name=self.name,
            suffix="_with_audio",
            extension=format_extension,
        )
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, filename)
        return VideoUrlArtifact(url)

    def _cleanup_temp_file(self, file_path: Path) -> None:
        """Clean up temporary file with error handling."""
        try:
            file_path.unlink(missing_ok=True)
        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Failed to clean up temporary file: {e}\n")

    def _run_ffmpeg_command(self, cmd: list[str], timeout: int = 300) -> None:
        """Run FFmpeg command with common error handling."""
        self.append_value_to_parameter("logs", f"Running ffmpeg command: {' '.join(cmd)}\n")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)  # noqa: S603
            if result.stdout:
                self.append_value_to_parameter("logs", f"FFmpeg stdout: {result.stdout}\n")
            if result.stderr:
                self.append_value_to_parameter("logs", f"FFmpeg stderr: {result.stderr}\n")
        except subprocess.TimeoutExpired as e:
            error_msg = f"FFmpeg process timed out after {timeout} seconds"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg error: {e.stderr}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def process(self) -> AsyncResult[None]:
        """Add audio to video with specified settings."""
        # Get and validate inputs
        video = self.parameter_values.get("video")
        audio = self.parameter_values.get("audio")

        video_artifact = to_video_artifact(video)
        audio_artifact = to_audio_artifact(audio)

        video_url = video_artifact.value
        audio_url = audio_artifact.value

        # Detect formats
        video_format = detect_video_format(video) or "mp4"
        audio_format = detect_audio_format(audio) or "mp3"

        self.append_value_to_parameter("logs", f"Detected video format: {video_format}\n")
        self.append_value_to_parameter("logs", f"Detected audio format: {audio_format}\n")

        try:
            # Run the processing asynchronously
            self.append_value_to_parameter("logs", "[Started adding audio to video..]\n")
            yield lambda: self._process_add_audio(video_url, audio_url, video_format)
            self.append_value_to_parameter("logs", "[Finished adding audio to video.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error adding audio to video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def _process_add_audio(self, video_url: str, audio_url: str, video_format: str) -> None:
        """Process the video and audio to add audio track."""
        # Validate URLs
        self._validate_url_safety(video_url)
        self._validate_audio_url_safety(audio_url)

        # Get FFmpeg paths
        _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

        # Detect video properties
        video_duration = self._detect_video_duration(video_url, ffprobe_path)
        has_video_audio = self._detect_audio_stream(video_url, ffprobe_path)
        audio_duration = self._detect_audio_duration(audio_url, ffprobe_path)

        self.append_value_to_parameter("logs", f"Video duration: {video_duration}s\n")
        self.append_value_to_parameter("logs", f"Audio duration: {audio_duration}s\n")
        self.append_value_to_parameter("logs", f"Video has audio: {'Yes' if has_video_audio else 'No'}\n")

        # Create temporary output file
        with tempfile.NamedTemporaryFile(suffix=f".{video_format}", delete=False) as temp_file:
            temp_output_path = Path(temp_file.name)

        try:
            # Get parameters for filter config
            loop_audio = self.get_parameter_value("loop_audio") or False
            audio_volume = self.get_parameter_value("audio_volume") or self.DEFAULT_VOLUME
            audio_start_time = self.get_parameter_value("audio_start_time") or 0.0
            loop_phase_offset = self.get_parameter_value("loop_phase_offset") or 0.0
            fade_type = self.get_parameter_value("fade_type") or self.DEFAULT_FADE_TYPE
            fade_in_duration = self.get_parameter_value("fade_in_duration") or 1.0
            fade_out_duration = self.get_parameter_value("fade_out_duration") or 1.0

            # Create filter configuration
            filter_config = AudioFilterConfig(
                audio_duration=audio_duration,
                video_duration=video_duration,
                loop_audio=loop_audio,
                audio_start_time=audio_start_time,
                loop_phase_offset=loop_phase_offset,
                audio_volume=audio_volume,
                fade_type=fade_type,
                fade_in_duration=fade_in_duration,
                fade_out_duration=fade_out_duration,
            )

            # Build and run FFmpeg command
            cmd = self._build_ffmpeg_command(
                video_url=video_url,
                audio_url=audio_url,
                output_path=str(temp_output_path),
                filter_config=filter_config,
                has_video_audio=has_video_audio,
            )

            self._run_ffmpeg_command(cmd, timeout=600)

            # Validate output file
            if not temp_output_path.exists() or temp_output_path.stat().st_size == 0:
                error_msg = "FFmpeg did not create output file or file is empty"
                raise ValueError(error_msg)

            # Read the output video
            with temp_output_path.open("rb") as f:
                video_bytes = f.read()

            # Save as VideoUrlArtifact
            output_artifact = self._save_video_artifact(video_bytes, video_format)

            # Set the output parameter
            self.parameter_output_values["output"] = output_artifact

            self.append_value_to_parameter("logs", f"Successfully added audio to video (format: {video_format})\n")

        finally:
            # Clean up temporary file
            self._cleanup_temp_file(temp_output_path)
