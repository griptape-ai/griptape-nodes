import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.video_utils import (
    detect_video_format,
    to_video_artifact,
    validate_url,
)


@dataclass(frozen=True)
class ResizeSettings:
    resize_mode: str
    percentage: float
    target_size: int
    target_width: int
    target_height: int
    fit_mode: str
    background_color: str
    scaling_algorithm: str
    lanczos_parameter: float


class ResizeVideo(ControlNode):
    """Resize a video with multiple scaling modes using FFmpeg."""

    RESIZE_MODE_WIDTH = "width"
    RESIZE_MODE_HEIGHT = "height"
    RESIZE_MODE_PERCENTAGE = "percentage"
    RESIZE_MODE_WIDTH_HEIGHT = "width and height"

    MIN_TARGET_SIZE = 1
    MAX_TARGET_SIZE = 8000
    DEFAULT_TARGET_SIZE = 1000
    MIN_EVEN_DIMENSION = 2

    MIN_PERCENTAGE_SCALE = 1
    MAX_PERCENTAGE_SCALE = 500
    DEFAULT_PERCENTAGE_SCALE = 100

    FIT_MODE_FIT = "fit"
    FIT_MODE_FILL = "fill"
    FIT_MODE_STRETCH = "stretch"

    HEX_SHORT_LENGTH = 3
    HEX_FULL_LENGTH = 6

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            ParameterVideo(
                name="video",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to resize",
            )
        )

        with ParameterGroup(name="resize_settings", ui_options={"collapsed": False}) as resize_group:
            resize_mode_param = ParameterString(
                name="resize_mode",
                default_value=self.RESIZE_MODE_PERCENTAGE,
                tooltip="How to resize the video: by width, height, percentage, or width and height",
            )
            resize_mode_param.add_trait(
                Options(
                    choices=[
                        self.RESIZE_MODE_WIDTH,
                        self.RESIZE_MODE_HEIGHT,
                        self.RESIZE_MODE_WIDTH_HEIGHT,
                        self.RESIZE_MODE_PERCENTAGE,
                    ]
                )
            )

            target_size_param = ParameterInt(
                name="target_size",
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target size in pixels for width/height modes ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_size_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            target_width_param = ParameterInt(
                name="target_width",
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target width in pixels ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_width_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            target_height_param = ParameterInt(
                name="target_height",
                default_value=self.DEFAULT_TARGET_SIZE,
                tooltip=f"Target height in pixels ({self.MIN_TARGET_SIZE}-{self.MAX_TARGET_SIZE})",
            )
            target_height_param.add_trait(Slider(min_val=self.MIN_TARGET_SIZE, max_val=self.MAX_TARGET_SIZE))

            fit_mode_param = ParameterString(
                name="fit_mode",
                default_value=self.FIT_MODE_FIT,
                tooltip="How to fit the video within the target dimensions",
            )
            fit_mode_param.add_trait(
                Options(
                    choices=[
                        self.FIT_MODE_FIT,
                        self.FIT_MODE_FILL,
                        self.FIT_MODE_STRETCH,
                    ]
                )
            )

            background_color_param = ParameterString(
                name="background_color",
                default_value="#000000",
                tooltip="Background color for letterboxing/matting",
            )
            background_color_param.add_trait(ColorPicker(format="hex"))

            # Add percentage parameter
            percentage_parameter = ParameterInt(
                name="percentage",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=self.DEFAULT_PERCENTAGE_SCALE,
                tooltip="Resize percentage (e.g., 50 for 50%)",
            )
            percentage_parameter.add_trait(Slider(min_val=self.MIN_PERCENTAGE_SCALE, max_val=self.MAX_PERCENTAGE_SCALE))

            # Add scaling algorithm parameter
            scaling_algorithm_parameter = ParameterString(
                name="scaling_algorithm",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="The scaling algorithm to use",
                default_value="bicubic",
            )
            scaling_algorithm_parameter.add_trait(
                Options(
                    choices=[
                        "neighbor",
                        "bilinear",
                        "bicubic",
                        "lanczos",
                    ]
                )
            )

            # Add lanczos parameter for fine-tuning lanczos algorithm
            lanczos_parameter = ParameterFloat(
                name="lanczos_parameter",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=3.0,
                tooltip="Lanczos algorithm parameter (alpha value, default: 3.0). Higher values (4-5) provide sharper results but may introduce ringing artifacts. Lower values (2-3) provide smoother results.",
                hide=True,
            )
            lanczos_parameter.add_trait(Slider(min_val=1.0, max_val=10.0))

        self.add_node_element(resize_group)

        self.hide_parameter_by_name("target_size")
        self.hide_parameter_by_name("target_width")
        self.hide_parameter_by_name("target_height")
        self.hide_parameter_by_name("fit_mode")
        self.hide_parameter_by_name("background_color")
        self.show_parameter_by_name("percentage")

        # Add output video parameter
        self.add_parameter(
            ParameterVideo(
                name="resized_video",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The resized video",
                pulse_on_run=True,
            )
        )
        # Group for logging information.
        with ParameterGroup(name="Logs") as logs_group:
            ParameterString(
                name="logs",
                tooltip="Displays processing logs and detailed events if enabled.",
                allowed_modes={ParameterMode.OUTPUT},
                multiline=True,
                placeholder_text="Logs",
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default.

        self.add_node_element(logs_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "resize_mode":
            if value == self.RESIZE_MODE_PERCENTAGE:
                self.show_parameter_by_name("percentage")
                self.hide_parameter_by_name("target_size")
                self.hide_parameter_by_name("target_width")
                self.hide_parameter_by_name("target_height")
                self.hide_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
            elif value == self.RESIZE_MODE_WIDTH_HEIGHT:
                self.hide_parameter_by_name("percentage")
                self.hide_parameter_by_name("target_size")
                self.show_parameter_by_name("target_width")
                self.show_parameter_by_name("target_height")
                self.show_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
            else:
                self.hide_parameter_by_name("percentage")
                self.show_parameter_by_name("target_size")
                self.hide_parameter_by_name("target_width")
                self.hide_parameter_by_name("target_height")
                self.hide_parameter_by_name("fit_mode")
                self.hide_parameter_by_name("background_color")
        elif parameter.name == "fit_mode":
            if value == self.FIT_MODE_FIT:
                self.show_parameter_by_name("background_color")
            else:
                self.hide_parameter_by_name("background_color")
        elif parameter.name == "scaling_algorithm":
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

        resize_mode = self.parameter_values.get("resize_mode", self.RESIZE_MODE_PERCENTAGE)
        percentage = self.parameter_values.get("percentage", self.DEFAULT_PERCENTAGE_SCALE)
        target_size = self.parameter_values.get("target_size", self.DEFAULT_TARGET_SIZE)
        target_width = self.parameter_values.get("target_width", self.DEFAULT_TARGET_SIZE)
        target_height = self.parameter_values.get("target_height", self.DEFAULT_TARGET_SIZE)

        if resize_mode in [self.RESIZE_MODE_WIDTH, self.RESIZE_MODE_HEIGHT] and (
            target_size < self.MIN_TARGET_SIZE or target_size > self.MAX_TARGET_SIZE
        ):
            msg = f"{self.name}: Target size must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_size}"
            exceptions.append(ValueError(msg))

        if resize_mode == self.RESIZE_MODE_PERCENTAGE and (
            percentage < self.MIN_PERCENTAGE_SCALE or percentage > self.MAX_PERCENTAGE_SCALE
        ):
            msg = f"{self.name}: Percentage must be between {self.MIN_PERCENTAGE_SCALE} and {self.MAX_PERCENTAGE_SCALE}, got {percentage}"
            exceptions.append(ValueError(msg))

        if resize_mode == self.RESIZE_MODE_WIDTH_HEIGHT:
            if target_width < self.MIN_TARGET_SIZE or target_width > self.MAX_TARGET_SIZE:
                msg = f"{self.name}: Target width must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_width}"
                exceptions.append(ValueError(msg))
            if target_height < self.MIN_TARGET_SIZE or target_height > self.MAX_TARGET_SIZE:
                msg = f"{self.name}: Target height must be between {self.MIN_TARGET_SIZE} and {self.MAX_TARGET_SIZE}, got {target_height}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _build_scale_expression(self, settings: ResizeSettings) -> str:
        flags = settings.scaling_algorithm
        if settings.scaling_algorithm == "lanczos":
            flags = f"{settings.scaling_algorithm}:param0={settings.lanczos_parameter}"

        if settings.resize_mode == self.RESIZE_MODE_WIDTH:
            even_width = self._make_even(settings.target_size)
            return f"scale={even_width}:-2:flags={flags}"

        if settings.resize_mode == self.RESIZE_MODE_HEIGHT:
            even_height = self._make_even(settings.target_size)
            return f"scale=-2:{even_height}:flags={flags}"

        if settings.resize_mode == self.RESIZE_MODE_PERCENTAGE:
            scale_factor = settings.percentage / 100.0
            return f"scale=trunc(iw*{scale_factor}/2)*2:trunc(ih*{scale_factor}/2)*2:flags={flags}"

        if settings.resize_mode == self.RESIZE_MODE_WIDTH_HEIGHT:
            even_width = self._make_even(settings.target_width)
            even_height = self._make_even(settings.target_height)

            if settings.fit_mode == self.FIT_MODE_STRETCH:
                return f"scale={even_width}:{even_height}:flags={flags}"

            if settings.fit_mode == self.FIT_MODE_FILL:
                return (
                    f"scale={even_width}:{even_height}:force_original_aspect_ratio=increase:"
                    f"flags={flags},crop={even_width}:{even_height}"
                )

            pad_color = self._format_ffmpeg_color(settings.background_color)
            return (
                f"scale={even_width}:{even_height}:force_original_aspect_ratio=decrease:"
                f"flags={flags},pad={even_width}:{even_height}:x=(ow-iw)/2:y=(oh-ih)/2:color={pad_color}"
            )

        error_msg = f"{self.name}: Invalid resize mode: {settings.resize_mode}"
        raise ValueError(error_msg)

    def _make_even(self, value: int) -> int:
        even_value = (max(1, value) // 2) * 2
        if even_value < self.MIN_EVEN_DIMENSION:
            return self.MIN_EVEN_DIMENSION
        return even_value

    def _format_ffmpeg_color(self, color_value: str) -> str:
        if not color_value:
            return "0xFFFFFF"

        cleaned = color_value.lstrip("#")
        if len(cleaned) == self.HEX_SHORT_LENGTH:
            cleaned = "".join([c * 2 for c in cleaned])
        if len(cleaned) != self.HEX_FULL_LENGTH:
            return "0xFFFFFF"
        return f"0x{cleaned}"

    def _resize_video_with_ffmpeg(
        self,
        input_url: str,
        output_path: str,
        settings: ResizeSettings,
    ) -> None:
        """Resize video using imageio_ffmpeg and ffmpeg."""

        def _validate_and_raise_if_invalid(url: str) -> None:
            if not validate_url(url):
                msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
                raise ValueError(msg)

        try:
            # Validate URL before using in subprocess
            _validate_and_raise_if_invalid(input_url)

            scale_expr = self._build_scale_expression(settings)

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
        detected_format: str,
        settings: ResizeSettings,
    ) -> None:
        """Performs the synchronous video resizing operation."""
        # Create temporary output file
        with tempfile.NamedTemporaryFile(suffix=f".{detected_format}", delete=False) as output_file:
            output_path = output_file.name

        try:
            self.append_value_to_parameter("logs", f"Resizing video using mode: {settings.resize_mode}\n")

            # Resize video directly from URL
            self._resize_video_with_ffmpeg(
                input_url=input_url,
                output_path=output_path,
                settings=settings,
            )

            # Read resized video
            with Path(output_path).open("rb") as f:
                resized_video_bytes = f.read()

            # Extract original filename from URL and create new filename
            original_filename = Path(input_url).stem  # Get filename without extension
            filename = f"{original_filename}_resized_{settings.scaling_algorithm}.{detected_format}"
            url = GriptapeNodes.StaticFilesManager().save_static_file(
                resized_video_bytes, filename, use_direct_save=True
            )

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
        settings = ResizeSettings(
            resize_mode=self.parameter_values.get("resize_mode", self.RESIZE_MODE_PERCENTAGE),
            percentage=self.parameter_values.get("percentage", self.DEFAULT_PERCENTAGE_SCALE),
            target_size=self.parameter_values.get("target_size", self.DEFAULT_TARGET_SIZE),
            target_width=self.parameter_values.get("target_width", self.DEFAULT_TARGET_SIZE),
            target_height=self.parameter_values.get("target_height", self.DEFAULT_TARGET_SIZE),
            fit_mode=self.parameter_values.get("fit_mode", self.FIT_MODE_FIT),
            background_color=self.parameter_values.get("background_color", "#000000"),
            scaling_algorithm=self.parameter_values.get("scaling_algorithm", "bicubic"),
            lanczos_parameter=self.parameter_values.get("lanczos_parameter", 3.0),
        )
        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing video resize..]\n")
        self.append_value_to_parameter("logs", f"Scaling algorithm: {settings.scaling_algorithm}\n")
        if settings.scaling_algorithm == "lanczos":
            self.append_value_to_parameter("logs", f"Lanczos parameter: {settings.lanczos_parameter}\n")

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
            yield lambda: self._process(
                input_url=input_url,
                detected_format=detected_format,
                settings=settings,
            )
            self.append_value_to_parameter("logs", "[Finished video processing.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error resizing video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
