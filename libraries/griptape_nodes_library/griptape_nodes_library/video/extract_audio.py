import tempfile
from pathlib import Path
from typing import Any, ClassVar

from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.traits.options import Options
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class ExtractAudio(BaseVideoProcessor):
    """Extract audio from a video and output it as an AudioUrlArtifact."""

    # Audio format options
    AUDIO_FORMATS: ClassVar[list[str]] = ["mp3", "wav", "aac", "flac", "ogg", "m4a"]
    DEFAULT_AUDIO_FORMAT = "mp3"

    # Audio quality options for lossy formats
    AUDIO_QUALITY_OPTIONS: ClassVar[dict[str, str]] = {
        "high": "128k",
        "medium": "96k",
        "low": "64k",
        "copy": "copy",  # Copy original audio stream without re-encoding
    }
    DEFAULT_AUDIO_QUALITY = "high"

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Hide parameters that aren't relevant for audio extraction
        self.hide_parameter_by_name("output_frame_rate")
        self.hide_parameter_by_name("processing_speed")
        self.hide_parameter_by_name("output")

        # Add audio output parameter
        self.add_parameter(
            Parameter(
                name="extracted_audio",
                output_type="AudioUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The audio extracted from the video",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters for audio extraction."""
        with ParameterGroup(name="audio_settings", ui_options={"collapsed": False}) as audio_group:
            # Audio format parameter
            format_param = Parameter(
                name="audio_format",
                type="str",
                default_value=self.DEFAULT_AUDIO_FORMAT,
                tooltip="Output audio format",
            )
            format_param.add_trait(Options(choices=self.AUDIO_FORMATS))
            self.add_parameter(format_param)

            # Audio quality parameter
            quality_param = Parameter(
                name="audio_quality",
                type="str",
                default_value=self.DEFAULT_AUDIO_QUALITY,
                tooltip="Audio quality/bitrate. Use 'copy' to avoid re-encoding (fastest, preserves original quality)",
            )
            quality_param.add_trait(Options(choices=list(self.AUDIO_QUALITY_OPTIONS.keys())))
            self.add_parameter(quality_param)

        self.add_node_element(audio_group)

    def _get_processing_description(self) -> str:
        """Get a description of what this processor does."""
        return "extracting audio from video"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build the FFmpeg command for extracting audio."""
        # Get FFmpeg paths from base class
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        audio_format = kwargs.get("audio_format", self.DEFAULT_AUDIO_FORMAT)
        audio_quality = kwargs.get("audio_quality", self.DEFAULT_AUDIO_QUALITY)

        # Base command - extract audio only (no video)
        cmd = [
            ffmpeg_path,
            "-i",
            input_url,  # Input video URL
            "-vn",  # No video stream
        ]

        # Handle audio encoding based on quality setting
        bitrate = self.AUDIO_QUALITY_OPTIONS[audio_quality]

        if bitrate == "copy":
            # Copy audio stream without re-encoding (fastest, preserves quality)
            cmd.extend(["-acodec", "copy"])
        elif audio_format in ["mp3"]:
            cmd.extend(["-acodec", "libmp3lame", "-b:a", bitrate])
        elif audio_format in ["aac", "m4a"]:
            cmd.extend(["-acodec", "aac", "-b:a", bitrate])
        elif audio_format in ["wav"]:
            cmd.extend(["-acodec", "pcm_s16le"])  # Uncompressed WAV
        elif audio_format in ["flac"]:
            cmd.extend(["-acodec", "flac"])  # Lossless compression
        elif audio_format in ["ogg"]:
            cmd.extend(["-acodec", "libvorbis", "-b:a", bitrate])
        else:
            # Default to AAC for unknown formats
            cmd.extend(["-acodec", "aac", "-b:a", bitrate])

        # Add output file
        cmd.extend(
            [
                "-y",  # Overwrite output file without asking
                output_path,  # Output path
            ]
        )

        return cmd

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate audio extraction parameters."""
        exceptions = []

        audio_format = self.get_parameter_value("audio_format")
        if audio_format and audio_format not in self.AUDIO_FORMATS:
            msg = f"{self.name} - Audio format must be one of {self.AUDIO_FORMATS}, got {audio_format}"
            exceptions.append(ValueError(msg))

        audio_quality = self.get_parameter_value("audio_quality")
        if audio_quality and audio_quality not in self.AUDIO_QUALITY_OPTIONS:
            msg = f"{self.name} - Audio quality must be one of {list(self.AUDIO_QUALITY_OPTIONS.keys())}, got {audio_quality}"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get audio extraction parameters."""
        return {
            "audio_format": self.get_parameter_value("audio_format"),
            "audio_quality": self.get_parameter_value("audio_quality"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get the output filename suffix."""
        audio_format = kwargs.get("audio_format", self.DEFAULT_AUDIO_FORMAT)
        audio_quality = kwargs.get("audio_quality", self.DEFAULT_AUDIO_QUALITY)
        return f"_extracted_audio_{audio_format}_{audio_quality}"

    def _save_audio_artifact(self, audio_bytes: bytes, format_extension: str, suffix: str = "") -> AudioUrlArtifact:
        """Save audio bytes to static file and return AudioUrlArtifact."""
        import uuid

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Generate meaningful filename
        filename = f"extracted_audio{suffix}_{uuid.uuid4().hex[:8]}.{format_extension}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(audio_bytes, filename)
        return AudioUrlArtifact(url)

    def process(self) -> AsyncResult[None]:
        """Extract audio from the input video and save as AudioUrlArtifact."""
        # Get video input data from base class
        input_url, detected_format = self._get_video_input_data()
        self._log_format_detection(detected_format)

        # Get custom parameters
        custom_params = self._get_custom_parameters()

        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing audio extraction..]\n")

        try:
            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started extracting audio..]\n")
            yield lambda: self._process_extract_audio(input_url, **custom_params)
            self.append_value_to_parameter("logs", "[Finished extracting audio.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error extracting audio: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def _process_extract_audio(self, input_url: str, **kwargs) -> None:
        """Extract audio and save as AudioUrlArtifact."""

        def _validate_output_file(file_path: Path) -> None:
            """Validate that the output file was created successfully."""
            if not file_path.exists() or file_path.stat().st_size == 0:
                error_msg = "FFmpeg did not create output file or file is empty"
                raise ValueError(error_msg)

        def _raise_no_audio_error() -> None:
            """Raise no audio stream error."""
            error_msg = "No audio stream found in the input video"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg)

        # Get parameters from kwargs
        audio_format = kwargs.get("audio_format", self.DEFAULT_AUDIO_FORMAT)
        audio_quality = kwargs.get("audio_quality", self.DEFAULT_AUDIO_QUALITY)

        # Create temporary output file for the extracted audio
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as temp_file:
            temp_audio_path = Path(temp_file.name)

        try:
            self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

            # Validate URL before using in subprocess
            self._validate_url_safety(input_url)

            # Get FFmpeg paths
            _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

            # Detect input video properties (required by base class interface)
            input_frame_rate, _, _ = self._detect_video_properties(input_url, ffprobe_path)

            # Check if video has audio stream
            has_audio = self._detect_audio_stream(input_url, ffprobe_path)
            if not has_audio:
                _raise_no_audio_error()

            self.append_value_to_parameter("logs", "✅ Audio stream detected in video\n")

            # Build the FFmpeg command for extracting audio
            cmd = self._build_ffmpeg_command(
                input_url,
                str(temp_audio_path),
                input_frame_rate,
                audio_format=audio_format,
                audio_quality=audio_quality,
            )

            # Use base class method to run FFmpeg command
            self._run_ffmpeg_command(cmd, timeout=300)

            # Check if output file was created
            _validate_output_file(temp_audio_path)

            # Read the extracted audio
            with temp_audio_path.open("rb") as f:
                audio_bytes = f.read()

            # Get output suffix
            suffix = self._get_output_suffix(**kwargs)

            # Save as AudioUrlArtifact
            audio_artifact = self._save_audio_artifact(audio_bytes, audio_format, suffix)

            # Set the output parameter
            self.parameter_output_values["extracted_audio"] = audio_artifact

            self.append_value_to_parameter("logs", f"Successfully extracted audio as {audio_format}\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error extracting audio: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
        finally:
            # Clean up temporary file using base class method
            self._cleanup_temp_file(temp_audio_path)
