import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
import static_ffmpeg.run  # type: ignore[import-untyped]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.video_utils import (
    detect_video_format,
    dict_to_video_url_artifact,
    to_video_artifact,
    validate_url,
)


class BaseVideoProcessor(SuccessFailureNode, ABC):
    """Base class for video processing nodes with common functionality."""

    # Default video properties constants
    DEFAULT_FRAME_RATE = 30.0
    DEFAULT_WIDTH = 1920
    DEFAULT_HEIGHT = 1080
    DEFAULT_DURATION = 0.0

    # Common frame rate options for different platforms
    FRAME_RATE_OPTIONS: ClassVar[dict[str, str]] = {
        "auto": "Auto (use input frame rate)",
        "24": "24 fps (Film)",
        "25": "25 fps (PAL)",
        "29.97": "29.97 fps (NTSC)",
        "30": "30 fps (YouTube, Web)",
        "50": "50 fps (PAL HD)",
        "59.94": "59.94 fps (NTSC HD)",
        "60": "60 fps (YouTube, Web HD)",
    }

    # Frame rate tolerance for comparison (in fps)
    FRAME_RATE_TOLERANCE: ClassVar[float] = 0.01

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoUrlArtifact", "VideoArtifact"],
                type="VideoUrlArtifact",
                tooltip="The video to process",
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Video or Path to Video",
                },
                converters=[self._convert_video_input],
            )
        )

        self._setup_custom_parameters()

        # Add frame rate parameter
        frame_rate_param = Parameter(
            name="output_frame_rate",
            type="str",
            default_value="auto",
            tooltip="Output frame rate. Choose 'auto' to preserve input frame rate, or select a specific rate for your target platform.",
        )
        frame_rate_param.add_trait(Options(choices=list(self.FRAME_RATE_OPTIONS.keys())))
        self.add_parameter(frame_rate_param)

        # Add processing speed parameter
        speed_param = Parameter(
            name="processing_speed",
            type="str",
            default_value="balanced",
            tooltip="Processing speed vs quality trade-off",
        )
        speed_param.add_trait(Options(choices=["fast", "balanced", "quality"]))
        self.add_parameter(speed_param)

        self.add_parameter(
            Parameter(
                name="output",
                output_type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The processed video",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        self._setup_logging_group()

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the video processing operation result",
            result_details_placeholder="Details on the processing attempt will be presented here.",
        )

    @abstractmethod
    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this video processor. Override in subclasses."""

    @abstractmethod
    def _get_processing_description(self) -> str:
        """Get a description of what this processor does. Override in subclasses."""

    @abstractmethod
    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:
        """Build the FFmpeg command for this processor. Override in subclasses."""

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

    def _get_ffmpeg_paths(self) -> tuple[str, str]:
        """Get FFmpeg and FFprobe executable paths."""
        try:
            ffmpeg_path, ffprobe_path = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
            return ffmpeg_path, ffprobe_path  # noqa: TRY300
        except Exception as e:
            error_msg = f"FFmpeg not found. Please ensure static-ffmpeg is properly installed. Error: {e!s}"
            raise ValueError(error_msg) from e

    def _get_processing_speed_settings(self) -> tuple[str, str, int]:
        """Get FFmpeg settings based on processing speed preference."""
        speed = self.get_parameter_value("processing_speed") or "balanced"

        if speed == "fast":
            return "ultrafast", "yuv420p", 30  # Fastest encoding, lower quality
        if speed == "quality":
            return "slow", "yuv420p", 18  # Slowest encoding, highest quality
        # balanced
        return "medium", "yuv420p", 23  # Balanced speed and quality

    def _get_frame_rate_filter(self, input_frame_rate: float) -> str:
        """Get frame rate filter based on output frame rate setting."""
        output_frame_rate = self.get_parameter_value("output_frame_rate") or "auto"

        if output_frame_rate == "auto":
            return ""  # No frame rate conversion needed

        # Convert string to float
        target_fps = float(output_frame_rate)

        # If target is same as input (within tolerance), no conversion needed
        if abs(target_fps - input_frame_rate) < self.FRAME_RATE_TOLERANCE:
            return ""

        # Return fps filter for frame rate conversion
        return f"fps=fps={target_fps}:round=up"

    def _combine_video_filters(self, custom_filter: str, input_frame_rate: float) -> str:
        """Combine custom video filter with frame rate filter if needed."""
        frame_rate_filter = self._get_frame_rate_filter(input_frame_rate)

        if not frame_rate_filter:
            return custom_filter

        if not custom_filter or custom_filter == "null":
            return frame_rate_filter

        # Combine filters with comma separator
        return f"{custom_filter},{frame_rate_filter}"

    def _detect_video_properties(self, input_url: str, ffprobe_path: str) -> tuple[float, tuple[int, int], float]:
        """Detect video frame rate, resolution, and duration."""
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

            # URL is validated via _validate_url_safety() before this call
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)  # noqa: S603
            import json

            streams_data = json.loads(result.stdout)

            if streams_data.get("streams") and len(streams_data["streams"]) > 0:
                video_stream = streams_data["streams"][0]

                # Get frame rate
                fps_str = video_stream.get("r_frame_rate", "30/1")
                if "/" in fps_str:
                    num, den = map(int, fps_str.split("/"))
                    frame_rate = num / den
                else:
                    frame_rate = float(fps_str)

                # Get resolution
                width = int(video_stream.get("width", self.DEFAULT_WIDTH))
                height = int(video_stream.get("height", self.DEFAULT_HEIGHT))

                # Get duration
                duration_str = video_stream.get("duration", "0")
                duration = float(duration_str) if duration_str != "N/A" else self.DEFAULT_DURATION

                return frame_rate, (width, height), duration
            return self.DEFAULT_FRAME_RATE, (self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT), self.DEFAULT_DURATION  # noqa: TRY300

        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Could not detect video properties, using defaults: {e}\n")
            return self.DEFAULT_FRAME_RATE, (self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT), self.DEFAULT_DURATION

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
            # If there are audio streams, ffprobe will return "audio" for each stream
            return "audio" in result.stdout.strip()
        except subprocess.CalledProcessError:
            # If ffprobe fails, assume no audio
            return False
        except Exception:
            # If any other error, assume no audio
            return False

    def _convert_video_input(self, value: Any) -> Any:
        """Convert video input (dict or VideoUrlArtifact) to VideoUrlArtifact."""
        if isinstance(value, dict):
            return dict_to_video_url_artifact(value)
        return value

    def _validate_video_input(self) -> list[Exception] | None:
        """Common video input validation."""
        exceptions = []

        # Validate that we have a video
        video = self.parameter_values.get("video")
        if not video:
            msg = f"{self.name}: Video parameter is required"
            exceptions.append(ValueError(msg))

        # Make sure it's a video artifact (converter should have handled dict conversion)
        if not isinstance(video, VideoUrlArtifact):
            msg = f"{self.name}: Video parameter must be a VideoUrlArtifact"
            exceptions.append(ValueError(msg))

        # Make sure it has a value
        if hasattr(video, "value") and not video.value:  # type: ignore  # noqa: PGH003
            msg = f"{self.name}: Video parameter must have a value"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _validate_url_safety(self, url: str) -> None:
        """Validate that the URL is safe for ffmpeg processing."""
        if not validate_url(url):
            msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
            raise ValueError(msg)

    def _get_video_input_data(self) -> tuple[str, str]:
        """Get video input URL and detected format."""
        video = self.parameter_values.get("video")
        video_artifact = to_video_artifact(video)
        input_url = video_artifact.value

        detected_format = detect_video_format(video)
        if not detected_format:
            detected_format = "mp4"  # default fallback

        return input_url, detected_format

    def _create_temp_output_file(self, format_extension: str) -> tuple[str, Path]:
        """Create a temporary output file and return path."""
        with tempfile.NamedTemporaryFile(suffix=f".{format_extension}", delete=False) as output_file:
            output_path = Path(output_file.name)
        return str(output_path), output_path

    def _save_video_artifact(self, video_bytes: bytes, format_extension: str, suffix: str = "") -> VideoUrlArtifact:
        """Save video bytes to static file and return VideoUrlArtifact."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Generate meaningful filename based on workflow and node
        filename = self._generate_filename(suffix, format_extension)
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, filename)
        return VideoUrlArtifact(url)

    def _run_ffmpeg_command(self, cmd: list[str], timeout: int = 300) -> None:
        """Run FFmpeg command with common error handling."""
        self.append_value_to_parameter("logs", f"Running ffmpeg command: {' '.join(cmd)}\n")

        try:
            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=True, timeout=timeout
            )
            self.append_value_to_parameter("logs", f"FFmpeg stdout: {result.stdout}\n")
        except subprocess.TimeoutExpired as e:
            error_msg = f"FFmpeg process timed out after {timeout} seconds"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg error: {e.stderr}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def _cleanup_temp_file(self, file_path: Path) -> None:
        """Clean up temporary file with error handling."""
        try:
            file_path.unlink(missing_ok=True)
        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Failed to clean up temporary file: {e}\n")

    def _log_video_properties(self, frame_rate: float, resolution: tuple[int, int], duration: float) -> None:
        """Log detected video properties."""
        self.append_value_to_parameter(
            "logs", f"Detected video: {resolution[0]}x{resolution[1]} @ {frame_rate}fps, duration: {duration}s\n"
        )

    def _log_format_detection(self, detected_format: str) -> None:
        """Log detected video format."""
        self.append_value_to_parameter("logs", f"Detected video format: {detected_format}\n")

    def validate_before_node_run(self) -> list[Exception] | None:
        """Common video input validation."""
        exceptions = []

        # Use base class validation for video input
        base_exceptions = self._validate_video_input()
        if base_exceptions:
            exceptions.extend(base_exceptions)

        # Add custom validation from subclasses
        custom_exceptions = self._validate_custom_parameters()
        if custom_exceptions:
            exceptions.extend(custom_exceptions)

        return exceptions if exceptions else None

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate custom parameters. Override in subclasses if needed."""
        return None

    def _process_video(self, input_url: str, output_path: str, **kwargs) -> None:
        """Process video using the custom FFmpeg command from subclasses."""
        try:
            # Validate URL before using in subprocess
            self._validate_url_safety(input_url)

            # Get FFmpeg paths
            _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

            # Detect input video properties for frame rate handling
            input_frame_rate, _, _ = self._detect_video_properties(input_url, ffprobe_path)

            # Build the FFmpeg command using the subclass implementation
            cmd = self._build_ffmpeg_command(input_url, output_path, input_frame_rate=input_frame_rate, **kwargs)

            # Use base class method to run FFmpeg command
            self._run_ffmpeg_command(cmd, timeout=300)

        except Exception as e:
            error_msg = f"Error during video processing: {e!s}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def _process(self, input_url: str, detected_format: str, **kwargs) -> None:
        """Common processing wrapper."""
        # Create temporary output file using base class method
        output_path, output_path_obj = self._create_temp_output_file(detected_format)

        try:
            self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

            # Process video using the custom implementation
            self._process_video(input_url, output_path, **kwargs)

            # Read processed video
            with output_path_obj.open("rb") as f:
                output_bytes = f.read()

            # Get output suffix from subclass
            suffix = self._get_output_suffix(**kwargs)

            # Use base class method to save video artifact
            output_artifact = self._save_video_artifact(output_bytes, detected_format, suffix)

            self.append_value_to_parameter(
                "logs", f"Successfully processed video with suffix: {suffix}.{detected_format}\n"
            )

            # Save to parameter
            self.parameter_output_values["output"] = output_artifact
        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error processing video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
        finally:
            # Clean up temporary file using base class method
            self._cleanup_temp_file(output_path_obj)

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix. Override in subclasses if needed."""
        return ""

    def process(self) -> AsyncResult[None]:
        """Common async processing entry point."""
        # Clear execution status at start
        self._clear_execution_status()

        # Get video input data
        input_url, detected_format = self._get_video_input_data()
        self._log_format_detection(detected_format)

        # Get custom parameters from subclasses
        custom_params = self._get_custom_parameters()

        # Initialize logs
        self.append_value_to_parameter("logs", f"[Processing {self._get_processing_description()}..]\n")

        try:
            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started video processing..]\n")
            yield lambda: self._process(input_url, detected_format, **custom_params)
            self.append_value_to_parameter("logs", "[Finished video processing.]\n")

            # Report success
            result_details = f"Successfully processed video: {self._get_processing_description()}"
            self._set_status_results(was_successful=True, result_details=result_details)

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error processing video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")

            # Report failure
            failure_details = f"Video processing failed: {error_message}"
            self._set_status_results(was_successful=False, result_details=failure_details)

            # Handle failure exception (raises if no failure output connected)
            self._handle_failure_exception(ValueError(msg))

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing. Override in subclasses if needed."""
        return {}

    def _generate_filename(self, suffix: str = "", extension: str = "mp4") -> str:
        """Generate a meaningful filename based on workflow and node information."""
        return generate_filename(
            node_name=self.name,
            suffix=suffix,
            extension=extension,
        )
