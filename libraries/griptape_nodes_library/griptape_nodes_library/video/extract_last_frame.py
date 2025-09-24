import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes_library.utils.image_utils import save_pil_image_to_static_file
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor


class ExtractLastFrame(BaseVideoProcessor):
    """Extract the last frame from a video and output it as an ImageUrlArtifact."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Hide parameters that aren't relevant for frame extraction
        self.hide_parameter_by_name("output_frame_rate")
        self.hide_parameter_by_name("processing_speed")
        self.hide_parameter_by_name("output")

        # Add image output parameter
        self.add_parameter(
            Parameter(
                name="last_frame_image",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The last frame extracted from the video as an image",
                ui_options={"pulse_on_run": True, "expander": True},
            )
        )

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this video processor."""
        # No additional parameters needed for extracting last frame

    def _get_processing_description(self) -> str:
        """Get a description of what this processor does."""
        return "extracting last frame from video"

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build the FFmpeg command for extracting the last frame."""
        # Get FFmpeg paths from base class
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        # Use sseof to seek to near the end and extract one frame
        # -sseof -3: seek to 3 seconds before end of file (must come before -i)
        # -vsync 0: extract only 1 frame
        # -q:v 0: highest quality
        # -f image2: output as image format
        # -update 1: overwrite output file if it exists
        cmd = [
            ffmpeg_path,
            "-sseof",
            "-3",  # Seek to 3 seconds before end (BEFORE input)
            "-i",
            input_url,  # Input video URL
            "-vsync",
            "0",  # Extract 1 frame
            "-q:v",
            "0",  # Set quality to 0 (highest quality)
            "-f",
            "image2",  # Output as image
            "-update",
            "1",  # Overwrite existing file
            "-y",  # Overwrite output file without asking
            output_path,  # Output path
        ]

        return cmd

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix."""
        return "_last_frame"

    def process(self) -> AsyncResult[None]:
        """Extract the last frame from the input video and save as ImageUrlArtifact."""
        # Get video input data from base class
        input_url, detected_format = self._get_video_input_data()
        self._log_format_detection(detected_format)

        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing extract last frame..]\n")

        try:
            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started extracting last frame..]\n")
            yield lambda: self._process_extract_frame(input_url)
            self.append_value_to_parameter("logs", "[Finished extracting last frame.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error extracting last frame: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def _process_extract_frame(self, input_url: str) -> None:
        """Extract the last frame and save as ImageUrlArtifact."""

        def _validate_output_file(file_path: Path) -> None:
            """Validate that the output file was created successfully."""
            if not file_path.exists() or file_path.stat().st_size == 0:
                error_msg = "FFmpeg did not create output file or file is empty"
                raise ValueError(error_msg)

        # Create temporary output file for the extracted frame (PNG format)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_image_path = Path(temp_file.name)

        try:
            self.append_value_to_parameter("logs", f"{self._get_processing_description()}\n")

            # Validate URL before using in subprocess
            self._validate_url_safety(input_url)

            # Get FFmpeg paths
            _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()

            # Detect input video properties (required by base class interface)
            input_frame_rate, _, _ = self._detect_video_properties(input_url, ffprobe_path)

            # Build the FFmpeg command for extracting last frame
            cmd = self._build_ffmpeg_command(input_url, str(temp_image_path), input_frame_rate)

            # Use base class method to run FFmpeg command
            self._run_ffmpeg_command(cmd, timeout=300)

            # Check if output file was created
            _validate_output_file(temp_image_path)

            # Load the extracted frame as PIL Image
            last_frame_pil = Image.open(temp_image_path)

            # Save as ImageUrlArtifact using utility function
            image_artifact = save_pil_image_to_static_file(last_frame_pil, "PNG")

            # Set the output parameter
            self.parameter_output_values["last_frame_image"] = image_artifact

            self.append_value_to_parameter("logs", "Successfully extracted last frame as image\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error extracting last frame: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
        finally:
            # Clean up temporary file using base class method
            self._cleanup_temp_file(temp_image_path)
