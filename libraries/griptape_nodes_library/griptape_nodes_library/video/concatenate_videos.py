import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.video_utils import to_video_artifact
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class ConcatenateVideos(BaseVideoProcessor):
    """Concatenate multiple videos into a single video file using FFmpeg."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        # Initialize the base SuccessFailureNode first (skip BaseVideoProcessor custom init)
        SuccessFailureNode.__init__(self, name, metadata)

        # Add our custom video_inputs parameter first
        self.add_parameter(
            ParameterList(
                name="video_inputs",
                input_types=[
                    "VideoArtifact",
                    "VideoUrlArtifact",
                    "list[VideoArtifact]",
                    "list[VideoUrlArtifact]",
                ],
                default_value=[],
                tooltip="Connect individual videos or a list of videos to concatenate (supports both VideoArtifact and VideoUrlArtifact)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "Videos to Concatenate"},
            )
        )

        # Now call BaseVideoProcessor setup methods manually (but skip the video parameter)
        self._setup_custom_parameters()

        # Add frame rate parameter
        frame_rate_param = Parameter(
            name="output_frame_rate",
            type="str",
            default_value="auto",
            tooltip="Output frame rate. Choose 'auto' to preserve input frame rate, or select a specific rate for your target platform.",
        )
        frame_rate_param.add_trait(Options(choices=list(BaseVideoProcessor.FRAME_RATE_OPTIONS.keys())))
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

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                output_type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The processed video",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

        # Setup logging group
        self._setup_logging_group()

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the video concatenation operation result",
            result_details_placeholder="Details on the concatenation attempt will be presented here.",
        )

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
        """Setup custom parameters specific to video concatenation."""
        with ParameterGroup(name="concatenation_settings", ui_options={"collapsed": False}) as concat_group:
            # Output format parameter
            format_parameter = Parameter(
                name="output_format",
                type="str",
                default_value="mp4",
                tooltip="Output video format (mp4, avi, mov, mkv, webm)",
            )
            format_parameter.add_trait(Options(choices=["mp4", "avi", "mov", "mkv", "webm"]))
            self.add_parameter(format_parameter)

            # Video codec parameter
            codec_parameter = Parameter(
                name="video_codec",
                type="str",
                default_value="libx264",
                tooltip="Video codec for output (libx264 for H.264, libx265 for H.265, copy to avoid re-encoding)",
            )
            codec_parameter.add_trait(Options(choices=["libx264", "libx265", "libvpx-vp9", "copy"]))
            self.add_parameter(codec_parameter)

            # Audio codec parameter
            audio_codec_parameter = Parameter(
                name="audio_codec",
                type="str",
                default_value="aac",
                tooltip="Audio codec for output (aac, mp3, copy to avoid re-encoding)",
            )
            audio_codec_parameter.add_trait(Options(choices=["aac", "mp3", "libmp3lame", "copy"]))
            self.add_parameter(audio_codec_parameter)

        self.add_node_element(concat_group)

    def _get_processing_description(self) -> str:
        """Get description of what this processor does."""
        return "video concatenation"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build FFmpeg command for video concatenation."""
        # Get FFmpeg paths from base class
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        # Get parameters
        video_codec = kwargs.get("video_codec", "libx264")
        audio_codec = kwargs.get("audio_codec", "aac")
        concat_list_file = kwargs.get("concat_list_file", "")

        if not concat_list_file:
            error_msg = "concat_list_file is required for concatenation"
            raise ValueError(error_msg)

        # Build FFmpeg command for concatenation
        cmd = [
            ffmpeg_path,
            "-f",
            "concat",  # Use concat demuxer
            "-safe",
            "0",  # Allow unsafe file names
            "-i",
            concat_list_file,  # Input concat list file
            "-c:v",
            video_codec,  # Video codec
            "-c:a",
            audio_codec,  # Audio codec
        ]

        # Add frame rate filter if needed (from base class)
        filter_complex = self._get_frame_rate_filter(input_frame_rate)
        if filter_complex:
            cmd.extend(["-vf", filter_complex])

        # Add processing speed settings if not copying
        if video_codec != "copy":
            preset, pix_fmt, crf = self._get_processing_speed_settings()
            cmd.extend(
                [
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    pix_fmt,
                ]
            )

        # Add common options
        cmd.extend(
            [
                "-movflags",
                "+faststart",  # Optimize for web streaming
                "-y",  # Overwrite output file
                output_path,  # Output file
            ]
        )

        return cmd

    def validate_before_node_run(self) -> list[Exception] | None:
        """Override base class validation to use our custom video_inputs validation."""
        # Skip the base class video validation since we use video_inputs instead of video
        # Only use our custom validation for concatenation parameters
        return self._validate_custom_parameters()

    def _validate_custom_parameters(self) -> list[Exception] | None:
        """Validate concatenation parameters."""

        def _create_video_validation_error(message: str) -> ValueError:
            """Create video validation error."""
            return ValueError(f"{self.name}: {message}")

        exceptions = []
        min_video_count = 2

        # Validate video inputs
        video_inputs = self.get_parameter_list_value("video_inputs")
        if not video_inputs:
            exceptions.append(_create_video_validation_error("At least one video input is required"))
        elif len(video_inputs) < min_video_count:
            exceptions.append(
                _create_video_validation_error(f"At least {min_video_count} videos are required for concatenation")
            )

        # Validate format
        output_format = self.get_parameter_value("output_format")
        valid_formats = ["mp4", "avi", "mov", "mkv", "webm"]
        if output_format and output_format not in valid_formats:
            msg = f"Invalid output format '{output_format}'. Must be one of: {valid_formats}"
            exceptions.append(_create_video_validation_error(msg))

        return exceptions if exceptions else None

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {
            "video_inputs": self.get_parameter_list_value("video_inputs"),
            "output_format": self.get_parameter_value("output_format"),
            "video_codec": self.get_parameter_value("video_codec"),
            "audio_codec": self.get_parameter_value("audio_codec"),
        }

    def _get_output_suffix(self, **kwargs) -> str:
        """Get output filename suffix."""
        num_videos = len(kwargs.get("video_inputs", []))
        return f"_concatenated_{num_videos}_videos"

    def process(self) -> AsyncResult[None]:
        """Concatenate multiple videos and save as VideoUrlArtifact."""
        # Clear execution status at start
        self._clear_execution_status()

        # Get custom parameters
        custom_params = self._get_custom_parameters()
        video_inputs = custom_params["video_inputs"]

        # Initialize logs
        self.append_value_to_parameter("logs", f"[Processing concatenation of {len(video_inputs)} videos..]\n")

        try:
            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started video concatenation..]\n")
            yield lambda: self._process_concatenation(**custom_params)
            self.append_value_to_parameter("logs", "[Finished video concatenation.]\n")

        except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, httpx.HTTPError) as e:
            error_message = str(e)
            msg = f"{self.name}: Error concatenating videos: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")

            # Report failure
            failure_details = f"Video concatenation failed: {error_message}"
            self._set_status_results(was_successful=False, result_details=failure_details)

            # Handle failure exception (raises if no failure output connected)
            self._handle_failure_exception(ValueError(msg))

        # Report success (only reached if no exception)
        result_details = f"Successfully concatenated {len(video_inputs)} videos"
        self._set_status_results(was_successful=True, result_details=result_details)

    def _raise_download_error(self, message: str, cause: Exception | None = None) -> None:
        """Raise a download error with proper formatting."""
        if cause:
            raise ValueError(message) from cause
        raise ValueError(message)

    def _process_concatenation(self, video_inputs: list, output_format: str, **kwargs) -> None:
        """Process video concatenation."""
        # Create temporary output file
        output_path, output_path_obj = self._create_temp_output_file(output_format)
        temp_files = []
        concat_list_file = None

        try:
            self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

            # Prepare video inputs and create concat list
            try:
                temp_files, concat_list_file = self._prepare_video_inputs(video_inputs)
            except (ValueError, OSError, httpx.HTTPError) as e:
                error_message = str(e)
                msg = f"{self.name}: Error preparing video inputs: {error_message}"
                self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
                raise ValueError(msg) from e

            # Execute FFmpeg concatenation
            try:
                output_artifact = self._execute_ffmpeg_concatenation(
                    temp_files, concat_list_file, output_path, output_path_obj, output_format, **kwargs
                )
            except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                error_message = str(e)
                msg = f"{self.name}: Error executing FFmpeg concatenation: {error_message}"
                self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
                raise ValueError(msg) from e

            self.append_value_to_parameter("logs", f"Successfully concatenated {len(video_inputs)} videos\n")

            # Save to parameter
            self.parameter_output_values["output"] = output_artifact

        finally:
            self._cleanup_temp_files(temp_files, concat_list_file, output_path_obj)

    def _prepare_video_inputs(self, video_inputs: list) -> tuple[list[Path], Path]:
        """Prepare video inputs by downloading, resizing if needed, and creating concat list file."""
        # Create temporary directory for processing
        temp_dir = Path(tempfile.mkdtemp())
        concat_list_file = temp_dir / f"concat_list_{uuid.uuid4()}.txt"
        temp_files = []

        # Download all videos first
        downloaded_videos = self._download_all_videos(video_inputs, temp_dir, temp_files)

        # Check dimensions and resize if needed
        processed_videos = self._process_video_dimensions(downloaded_videos, temp_dir, temp_files)

        # Create concat list file
        self._create_concat_list(processed_videos, concat_list_file)

        # Debug: Log concat file contents
        self._log_concat_file_debug(concat_list_file)
        return temp_files, concat_list_file

    def _download_all_videos(self, video_inputs: list, temp_dir: Path, temp_files: list[Path]) -> list[Path]:
        """Download all input videos to temporary files."""

        def _create_input_validation_error(video_type: type) -> ValueError:
            """Create input validation error."""
            msg = f"Invalid video input type: {video_type}"
            return ValueError(msg)

        self.append_value_to_parameter("logs", "Downloading videos for concatenation...\n")
        downloaded_videos = []

        for i, video_input in enumerate(video_inputs):
            # Convert video input to VideoUrlArtifact (handles both VideoArtifact and VideoUrlArtifact)
            video_artifact = to_video_artifact(video_input)

            # Extract video URL from the normalized artifact
            if isinstance(video_input, str):
                video_url = video_input
            elif isinstance(video_artifact, VideoUrlArtifact) or hasattr(video_artifact, "value"):
                video_url = video_artifact.value
            else:
                raise _create_input_validation_error(type(video_input))

            # Validate URL
            self._validate_url_safety(video_url)

            # Create temporary file for each video
            temp_video_file = temp_dir / f"video_original_{i}_{uuid.uuid4()}.mp4"
            temp_files.append(temp_video_file)

            # Download video to temp file
            self._download_video(video_url, str(temp_video_file))
            downloaded_videos.append(temp_video_file)

            self.append_value_to_parameter("logs", f"Downloaded video {i + 1}/{len(video_inputs)}\n")

        return downloaded_videos

    def _process_video_dimensions(
        self, downloaded_videos: list[Path], temp_dir: Path, temp_files: list[Path]
    ) -> list[Path]:
        """Check video dimensions and resize if needed."""
        self.append_value_to_parameter("logs", "Checking video dimensions...\n")

        # Get dimensions of all videos
        video_dimensions = []
        for video_file in downloaded_videos:
            dimensions = self._get_video_dimensions(str(video_file))
            video_dimensions.append(dimensions)

        # Use first video's dimensions as target
        target_width, target_height = video_dimensions[0]
        self.append_value_to_parameter(
            "logs", f"Target dimensions (from first video): {target_width}x{target_height}\n"
        )

        # Check if all videos have the same dimensions
        all_same_size = all(dims == (target_width, target_height) for dims in video_dimensions)

        if all_same_size:
            self.append_value_to_parameter("logs", "✅ All videos have matching dimensions - no resizing needed\n")
            return downloaded_videos

        # Some videos need resizing
        self.append_value_to_parameter(
            "logs", "🔄 Videos have different dimensions - resizing to match first video...\n"
        )

        # Create resize context to reduce parameter count
        resize_context = {
            "downloaded_videos": downloaded_videos,
            "video_dimensions": video_dimensions,
            "target_width": target_width,
            "target_height": target_height,
            "temp_dir": temp_dir,
            "temp_files": temp_files,
        }
        return self._resize_mismatched_videos(resize_context)

    def _resize_mismatched_videos(self, resize_context: dict) -> list[Path]:
        """Resize videos that don't match the target dimensions."""
        # Extract context variables
        downloaded_videos = resize_context["downloaded_videos"]
        video_dimensions = resize_context["video_dimensions"]
        target_width = resize_context["target_width"]
        target_height = resize_context["target_height"]
        temp_dir = resize_context["temp_dir"]
        temp_files = resize_context["temp_files"]

        processed_videos = []

        for i, (video_file, dimensions) in enumerate(zip(downloaded_videos, video_dimensions, strict=True)):
            if i == 0:
                # First video is the target, use as-is
                processed_videos.append(video_file)
                self.append_value_to_parameter(
                    "logs", f"• Video {i + 1}: {dimensions[0]}x{dimensions[1]} (reference)\n"
                )
            elif dimensions == (target_width, target_height):
                # Same size as target, use as-is
                processed_videos.append(video_file)
                self.append_value_to_parameter(
                    "logs", f"• Video {i + 1}: {dimensions[0]}x{dimensions[1]} (no resize needed)\n"
                )
            else:
                # Resize this video
                resized_video_file = temp_dir / f"video_resized_{i}_{uuid.uuid4()}.mp4"
                temp_files.append(resized_video_file)

                self.append_value_to_parameter(
                    "logs",
                    f"• Video {i + 1}: {dimensions[0]}x{dimensions[1]} → {target_width}x{target_height} (resizing...)\n",
                )
                self._resize_video(str(video_file), str(resized_video_file), target_width, target_height)
                processed_videos.append(resized_video_file)
                self.append_value_to_parameter("logs", f"  ✅ Video {i + 1} resized successfully\n")

        return processed_videos

    def _create_concat_list(self, processed_videos: list[Path], concat_list_file: Path) -> None:
        """Create concat list file for FFmpeg."""
        self.append_value_to_parameter("logs", "Creating concatenation list...\n")
        with concat_list_file.open("w") as f:
            for video_file in processed_videos:
                # Add to concat list - use single quotes to avoid escaping issues
                file_path = str(video_file)
                concat_line = f"file '{file_path}'\n"
                f.write(concat_line)

                # Debug logging
                self.append_value_to_parameter("logs", f"Added to concat list: {concat_line.strip()}\n")

    def _log_concat_file_debug(self, concat_list_file: Path) -> None:
        """Log concat file contents for debugging."""
        self.append_value_to_parameter("logs", f"Concat list file path: {concat_list_file}\n")
        try:
            with concat_list_file.open("r") as debug_f:
                concat_contents = debug_f.read()
                self.append_value_to_parameter("logs", f"Concat file contents:\n{concat_contents}\n")
        except OSError as e:
            self.append_value_to_parameter("logs", f"Could not read concat file for debugging: {e}\n")

    def _execute_ffmpeg_concatenation(
        self,
        temp_files: list[Path],
        concat_list_file: Path,
        output_path: str,
        output_path_obj: Path,
        output_format: str,
        **kwargs,
    ) -> VideoUrlArtifact:
        """Execute FFmpeg concatenation and return output artifact."""

        def _validate_output_file(file_path: Path) -> None:
            """Validate that the output file was created successfully."""
            if not file_path.exists() or file_path.stat().st_size == 0:
                error_msg = "FFmpeg did not create output file or file is empty"
                raise ValueError(error_msg)

        # Detect properties from first video for frame rate handling
        _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
        first_video_url = str(temp_files[0]) if temp_files else ""
        input_frame_rate, _, _ = self._detect_video_properties(first_video_url, ffprobe_path)

        # Build the FFmpeg command for concatenation
        cmd = self._build_ffmpeg_command(
            "", output_path, input_frame_rate, concat_list_file=str(concat_list_file), **kwargs
        )

        # Use base class method to run FFmpeg command
        self.append_value_to_parameter("logs", "Running FFmpeg concatenation...\n")
        self.append_value_to_parameter("logs", f"FFmpeg command: {' '.join(cmd)}\n")
        self._run_ffmpeg_command(cmd, timeout=600)  # 10 minute timeout for large videos

        # Validate output file was created
        _validate_output_file(output_path_obj)

        # Read concatenated video
        with output_path_obj.open("rb") as f:
            output_bytes = f.read()

        # Get output suffix
        suffix = self._get_output_suffix(**kwargs)

        # Save video artifact
        return self._save_video_artifact(output_bytes, output_format, suffix)

    def _cleanup_temp_files(self, temp_files: list[Path], concat_list_file: Path | None, output_path_obj: Path) -> None:
        """Clean up temporary files after processing."""
        # Clean up temporary files
        for temp_file in temp_files:
            if isinstance(temp_file, Path):
                self._cleanup_temp_file(temp_file)
            else:
                self._cleanup_temp_file(Path(temp_file))

        if concat_list_file and concat_list_file.exists():
            try:
                concat_list_file.unlink()
            except OSError as e:
                self.append_value_to_parameter("logs", f"Warning: Failed to clean up concat list file: {e}\n")

        # Clean up main output file
        self._cleanup_temp_file(output_path_obj)

    def _download_video(self, video_url: str, output_path: str) -> None:
        """Download a video from URL to local file."""
        try:
            response = httpx.get(video_url, timeout=30.0)
            response.raise_for_status()

            output_file = Path(output_path)
            with output_file.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

            # Verify file was downloaded
            if not output_file.exists() or output_file.stat().st_size == 0:
                self._raise_download_error("Downloaded video file is empty or does not exist")

        except httpx.HTTPError as e:
            msg = f"Error downloading video from {video_url}: {e!s}"
            self._raise_download_error(msg, e)
        except OSError as e:
            msg = f"Error saving video to {output_path}: {e!s}"
            self._raise_download_error(msg, e)

    def _get_video_dimensions(self, video_path: str) -> tuple[int, int]:
        """Get video dimensions using ffprobe.

        Args:
            video_path: Path to the video file

        Returns:
            Tuple of (width, height)
        """

        def _raise_ffprobe_error(stderr: str) -> None:
            """Raise ffprobe command error."""
            error_msg = f"ffprobe command failed: {stderr}"
            raise ValueError(error_msg)

        def _raise_no_streams_error() -> None:
            """Raise no video streams error."""
            error_msg = "No video streams found in file"
            raise ValueError(error_msg)

        try:
            # Get FFmpeg paths from base class
            _, ffprobe_path = self._get_ffmpeg_paths()

            # Use ffprobe to get video information
            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "v:0",  # Select first video stream
                video_path,
            ]

            # Use subprocess directly for ffprobe since _run_ffmpeg_command is for ffmpeg only
            # ruff: noqa: S603 - subprocess call with controlled ffprobe path and validated video_path
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)

            if result.returncode != 0:
                _raise_ffprobe_error(result.stderr)

            # Parse JSON output
            probe_data = json.loads(result.stdout)

            # Get video stream information
            if not probe_data.get("streams"):
                _raise_no_streams_error()

            video_stream = probe_data["streams"][0]
            width = int(video_stream["width"])
            height = int(video_stream["height"])

            return (width, height)  # noqa: TRY300

        except json.JSONDecodeError as e:
            msg = f"Error parsing video information: {e!s}"
            raise ValueError(msg) from e
        except (KeyError, ValueError) as e:
            msg = f"Error extracting video dimensions: {e!s}"
            raise ValueError(msg) from e
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            msg = f"Error getting video dimensions: {e!s}"
            raise ValueError(msg) from e

    def _resize_video(self, input_path: str, output_path: str, target_width: int, target_height: int) -> None:
        """Resize a video to target dimensions using ffmpeg.

        Args:
            input_path: Path to the input video
            output_path: Path for the resized output video
            target_width: Target width in pixels
            target_height: Target height in pixels
        """

        def _raise_resize_output_error() -> None:
            """Raise resize output file error."""
            error_msg = "ffmpeg did not create resized video file or file is empty"
            raise ValueError(error_msg)

        try:
            # Get FFmpeg path from base class
            ffmpeg_path, _ = self._get_ffmpeg_paths()

            # Build ffmpeg command for resizing
            # Use scale filter with force_original_aspect_ratio=decrease to maintain aspect ratio
            # and pad with black bars if needed to reach exact target dimensions
            scale_filter = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease"
            pad_filter = f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
            video_filter = f"{scale_filter},{pad_filter}"

            cmd = [
                ffmpeg_path,
                "-i",
                input_path,
                "-vf",
                video_filter,
                "-c:a",
                "copy",  # Copy audio without re-encoding
                "-y",  # Overwrite output file
                output_path,
            ]

            # Run ffmpeg command with 5 minute timeout for resizing
            self._run_ffmpeg_command(cmd, timeout=300)

            # Check if output file was created
            output_file = Path(output_path)
            if not output_file.exists() or output_file.stat().st_size == 0:
                _raise_resize_output_error()

        except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            msg = f"Error resizing video: {e!s}"
            raise ValueError(msg) from e
