import subprocess
import tempfile
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.video_utils import (
    detect_video_format,
    to_video_artifact,
    validate_url,
)


class ResizeVideo(ControlNode):
    """Resize a video using imageio_ffmpeg by percentage."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to resize",
            )
        )

        # Add percentage parameter
        percentage_parameter = Parameter(
            name="percentage",
            type="int",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=50,
            tooltip="Resize percentage (e.g., 50 for 50%)",
        )
        self.add_parameter(percentage_parameter)
        percentage_parameter.add_trait(Slider(min_val=1, max_val=400))

        # Add scaling algorithm parameter
        scaling_algorithm_parameter = Parameter(
            name="scaling_algorithm",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="The scaling algorithm to use",
            default_value="bicubic",
        )
        self.add_parameter(scaling_algorithm_parameter)
        scaling_algorithm_parameter.add_trait(
            Options(
                choices=[
                    "fast_bilinear",
                    "bilinear",
                    "bicubic",
                    "experimental",
                    "neighbor",
                    "area",
                    "bicublin",
                    "gauss",
                    "sinc",
                    "lanczos",
                    "spline",
                    "print_info",
                    "accurate_rnd",
                    "full_chroma_int",
                    "full_chroma_inp",
                    "bitexact",
                ]
            )
        )

        # Add lanczos parameter for fine-tuning lanczos algorithm
        lanczos_parameter = Parameter(
            name="lanczos_parameter",
            type="float",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=3.0,
            tooltip="Lanczos algorithm parameter (alpha value, default: 3.0). Higher values (4-5) provide sharper results but may introduce ringing artifacts. Lower values (2-3) provide smoother results.",
            ui_options={"hide": True},
        )
        self.add_parameter(lanczos_parameter)
        lanczos_parameter.add_trait(Slider(min_val=1.0, max_val=10.0))

        # Add output video parameter
        self.add_parameter(
            Parameter(
                name="resized_video",
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The resized video",
                ui_options={"pulse_on_run": True},
            )
        )
        # Group for logging information.
        with ParameterGroup(name="Logs") as logs_group:
            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default.

        self.add_node_element(logs_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "scaling_algorithm":
            if value == "lanczos":
                self.show_parameter_by_name("lanczos_parameter")
            else:
                self.hide_parameter_by_name("lanczos_parameter")
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []

        # Validate that we have a video
        video = self.parameter_values.get("video")
        if not video:
            msg = f"{self.name}: Video parameter is required"
            exceptions.append(ValueError(msg))

        # Make sure it's a video artifact
        if not isinstance(video, VideoUrlArtifact):
            msg = f"{self.name}: Video parameter must be a VideoUrlArtifact"
            exceptions.append(ValueError(msg))

        # Make sure it has a value
        if hasattr(video, "value") and not video.value:  # type: ignore  # noqa: PGH003
            msg = f"{self.name}: Video parameter must have a value"
            exceptions.append(ValueError(msg))

        # Validate percentage
        percentage = self.parameter_values.get("percentage", 50)
        if percentage <= 0:
            msg = f"{self.name}: Percentage must be greater than 0"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _resize_video_with_ffmpeg(
        self,
        input_url: str,
        output_path: str,
        percentage: float,
        scaling_algorithm: str,
        lanczos_parameter: float = 3.0,
    ) -> None:
        """Resize video using imageio_ffmpeg and ffmpeg."""

        def _validate_and_raise_if_invalid(url: str) -> None:
            if not validate_url(url):
                msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
                raise ValueError(msg)

        try:
            # Validate URL before using in subprocess
            _validate_and_raise_if_invalid(input_url)

            # Create scale expression for percentage - ensure integer values and even dimensions
            if scaling_algorithm == "lanczos":
                # For lanczos, include the parameter value
                scale_expr = (
                    f"scale=trunc(trunc(iw*{percentage / 100})/2)*2:"
                    f"trunc(trunc(ih*{percentage / 100})/2)*2:"
                    f"flags={scaling_algorithm}:param0={lanczos_parameter}"
                )
            else:
                # For other algorithms, use standard flags
                scale_expr = (
                    f"scale=trunc(trunc(iw*{percentage / 100})/2)*2:"
                    f"trunc(trunc(ih*{percentage / 100})/2)*2:"
                    f"flags={scaling_algorithm}"
                )

                # Get ffmpeg executable path from static-ffmpeg dependency
            ffmpeg_path, _ = run.get_or_fetch_platform_executables_else_raise()

            # Build ffmpeg command - ffmpeg can work directly with URLs
            cmd = [
                ffmpeg_path,
                "-y",
                "-i",
                input_url,
                "-vf",
                scale_expr,
                "-c:a",
                "copy",
                output_path,
            ]

            self.append_value_to_parameter("logs", f"Running ffmpeg command: {' '.join(cmd)}\n")

            # Run ffmpeg with timeout
            try:
                result = subprocess.run(  # noqa: S603
                    cmd, capture_output=True, text=True, check=True, timeout=300
                )
                self.append_value_to_parameter("logs", f"FFmpeg stdout: {result.stdout}\n")
            except subprocess.TimeoutExpired as e:
                error_msg = "FFmpeg process timed out after 5 minutes"
                self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
                raise ValueError(error_msg) from e
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg error: {e.stderr}"
                self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
                raise ValueError(error_msg) from e

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg error: {e.stderr}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Error during video resize: {e!s}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def _process(
        self,
        input_url: str,
        percentage: float,
        detected_format: str,
        scaling_algorithm: str,
        lanczos_parameter: float = 3.0,
    ) -> None:
        """Performs the synchronous video resizing operation."""
        # Create temporary output file
        with tempfile.NamedTemporaryFile(suffix=f".{detected_format}", delete=False) as output_file:
            output_path = output_file.name

        try:
            self.append_value_to_parameter("logs", f"Resizing video to {percentage}% of original size\n")

            # Resize video directly from URL
            self._resize_video_with_ffmpeg(input_url, output_path, percentage, scaling_algorithm, lanczos_parameter)

            # Read resized video
            with Path(output_path).open("rb") as f:
                resized_video_bytes = f.read()

            # Extract original filename from URL and create new filename
            original_filename = Path(input_url).stem  # Get filename without extension
            filename = f"{original_filename}_resized_{int(percentage)}_{scaling_algorithm}.{detected_format}"
            url = GriptapeNodes.StaticFilesManager().save_static_file(resized_video_bytes, filename)

            self.append_value_to_parameter("logs", f"Successfully resized video: {filename}\n")

            # Create output artifact and save to parameter
            resized_video_artifact = VideoUrlArtifact(url)
            self.parameter_output_values["resized_video"] = resized_video_artifact
        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error resizing video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
        finally:
            # Clean up temporary file
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception as e:
                self.append_value_to_parameter("logs", f"Warning: Failed to clean up temporary file: {e}\n")

    def process(self) -> AsyncResult[None]:
        """Executes the main logic of the node asynchronously."""
        video = self.parameter_values.get("video")
        percentage = self.parameter_values.get("percentage", 50.0)
        scaling_algorithm = self.parameter_values.get("scaling_algorithm", "bilinear")
        lanczos_parameter = self.parameter_values.get("lanczos_parameter", 3.0)
        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing video resize..]\n")
        self.append_value_to_parameter("logs", f"Scaling algorithm: {scaling_algorithm}\n")
        if scaling_algorithm == "lanczos":
            self.append_value_to_parameter("logs", f"Lanczos parameter: {lanczos_parameter}\n")

        try:
            # Convert to video artifact
            video_artifact = to_video_artifact(video)

            # Get the video URL directly. Note - we've validated this in validate_before_workflow_run.
            input_url = video_artifact.value

            # Detect video format for output filename
            detected_format = detect_video_format(video)
            if not detected_format:
                detected_format = "mp4"  # default fallback

            self.append_value_to_parameter("logs", f"Detected video format: {detected_format}\n")

            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started video processing..]\n")
            yield lambda: self._process(input_url, percentage, detected_format, scaling_algorithm, lanczos_parameter)
            self.append_value_to_parameter("logs", "[Finished video processing.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error resizing video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
