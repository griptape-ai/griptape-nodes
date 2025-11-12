import os
import re
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import save_pil_image_to_static_file
from griptape_nodes_library.utils.video_utils import to_video_artifact
from griptape_nodes_library.video.base_video_processor import BaseVideoProcessor

# Common resolution presets
RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1K (1024x1024)": (1024, 1024),
    "2K (2048x1080)": (2048, 1080),
    "4K (3840x2160)": (3840, 2160),
    "HD (1280x720)": (1280, 720),
    "Full HD (1920x1080)": (1920, 1080),
    "1280x1024": (1280, 1024),
    "1920x1200": (1920, 1200),
    "2560x1440": (2560, 1440),
}

# Constants for size parsing
K_RESOLUTION_1K = 1
K_RESOLUTION_2K = 2
K_RESOLUTION_4K = 4
K_BASE_SIZE = 1024
MIN_DIMENSION = 1

# Preview colors
PREVIEW_BG_COLOR = (128, 128, 128)  # Grey background fallback
PREVIEW_BG_OUTLINE = (255, 255, 255)  # White outline for original video
PREVIEW_CROP_OUTLINE = (0, 100, 255)  # Blue outline for cropped area

# Preview frame extraction settings (low resolution for speed)
PREVIEW_MAX_WIDTH = 800
PREVIEW_MAX_HEIGHT = 600
PREVIEW_WEBP_QUALITY = 60  # Lower quality for faster processing


def parse_size_string(size_str: str) -> tuple[int, int] | None:
    """Parse size string like '1k', '2k', '1280x1024', etc. into (width, height).

    Args:
        size_str: Size string to parse

    Returns:
        Tuple of (width, height) or None if parsing fails
    """
    if not size_str:
        return None

    size_str = size_str.strip().lower()

    # Check presets first
    for preset_name, dimensions in RESOLUTION_PRESETS.items():
        if preset_name.lower() == size_str.lower():
            return dimensions

    # Try to parse "WxH" format
    if "x" in size_str:
        return _parse_wxh_format(size_str)

    # Try to parse "Nk" format
    return _parse_k_format(size_str)


def _parse_wxh_format(size_str: str) -> tuple[int, int] | None:
    """Parse WxH format like '1280x1024'."""
    parts = size_str.split("x")
    expected_parts = 2
    if len(parts) != expected_parts:
        return None

    try:
        width = int(parts[0].strip())
        height = int(parts[1].strip())
        if width > 0 and height > 0:
            return (width, height)
    except ValueError:
        pass

    return None


def _parse_k_format(size_str: str) -> tuple[int, int] | None:
    """Parse Nk format like '1k', '2k', '4k'."""
    k_match = re.match(r"^(\d+)k$", size_str)
    if not k_match:
        return None

    k_value = int(k_match.group(1))

    # Common K resolutions
    if k_value == K_RESOLUTION_1K:
        return (1024, 1024)
    if k_value == K_RESOLUTION_2K:
        return (2048, 1080)
    if k_value == K_RESOLUTION_4K:
        return (3840, 2160)

    # Default: assume square
    base_size = k_value * K_BASE_SIZE
    return (base_size, base_size)


class CropVideo(BaseVideoProcessor):
    """Crop a video to a specific size with preview visualization."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Cache for first frame of video (for preview background)
        self._cached_first_frame: Image.Image | None = None
        self._cached_video_url: str | None = None

    def _setup_custom_parameters(self) -> None:
        """Setup custom parameters specific to this video processor."""
        # Add crop size parameter with presets
        size_param = Parameter(
            name="crop_size",
            type="str",
            default_value="Custom",
            tooltip="Target crop size. Choose a preset or enter custom dimensions (e.g., '1280x1024' or '2k')",
        )
        size_param.add_trait(Options(choices=[*list(RESOLUTION_PRESETS.keys()), "Custom"]))
        self.add_parameter(size_param)

        # Add custom width/height parameters (shown when Custom is selected)
        self.add_parameter(
            Parameter(
                name="custom_width",
                type="int",
                default_value=800,
                tooltip="Custom crop width in pixels",
            )
        )
        self.add_parameter(
            Parameter(
                name="custom_height",
                type="int",
                default_value=800,
                tooltip="Custom crop height in pixels",
            )
        )

        # Add crop position parameter (center, top-left, etc.)
        position_param = Parameter(
            name="crop_position",
            type="str",
            default_value="center",
            tooltip="Where to position the crop area",
        )
        position_param.add_trait(
            Options(
                choices=[
                    "center",
                    "top-left",
                    "top-right",
                    "bottom-left",
                    "bottom-right",
                    "top-center",
                    "bottom-center",
                    "left-center",
                    "right-center",
                ]
            )
        )
        self.add_parameter(position_param)

        # Add preview image output
        self.add_parameter(
            Parameter(
                name="preview",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Preview image showing the crop area overlaid on the first frame of the video",
                ui_options={"expander": True},
            )
        )

    def _get_processing_description(self) -> str:
        """Get a description of what this processor does."""
        return "cropping video"

    def _extract_first_frame(self, input_url: str) -> Image.Image | None:
        """Extract first frame from video at low resolution for preview.

        Args:
            input_url: URL or path to video file

        Returns:
            PIL Image of first frame, or None if extraction fails
        """
        try:
            self._validate_url_safety(input_url)
            ffmpeg_path, _ = self._get_ffmpeg_paths()

            # Create temporary file for frame extraction
            # Use mkstemp for better Windows compatibility
            fd, temp_path_str = tempfile.mkstemp(suffix=".webp")
            os.close(fd)  # Close file descriptor immediately
            temp_path = Path(temp_path_str)

            try:
                # Extract first frame at low resolution as WebP for speed
                # Use scale filter syntax that works on both Windows and Mac
                # Escape commas with backslashes for FFmpeg filter syntax
                scale_filter = f"scale=min({PREVIEW_MAX_WIDTH}\\,iw):min({PREVIEW_MAX_HEIGHT}\\,ih):force_original_aspect_ratio=decrease"

                cmd = [
                    ffmpeg_path,
                    "-y",
                    "-ss",
                    "0",
                    "-i",
                    input_url,
                    "-vframes",
                    "1",
                    "-vf",
                    scale_filter,
                    "-f",
                    "webp",
                    "-quality",
                    str(PREVIEW_WEBP_QUALITY),
                    str(temp_path),
                ]

                # Run ffmpeg with short timeout for preview extraction
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)  # noqa: S603

                # On Windows, wait a moment for file to be fully written
                time.sleep(0.1)

                # Load the extracted frame
                if temp_path.exists() and temp_path.stat().st_size > 0:
                    frame_image = Image.open(temp_path)
                    return frame_image

                # Log if file wasn't created
                error_msg = f"FFmpeg did not create output file. stderr: {result.stderr}"
                self.append_value_to_parameter("logs", f"Warning: {error_msg}\n")

            except subprocess.CalledProcessError as e:
                # Log the actual error for debugging
                error_msg = f"FFmpeg error: {e.stderr}"
                self.append_value_to_parameter("logs", f"Warning: Could not extract first frame: {error_msg}\n")
            finally:
                # Clean up temp file
                with suppress(Exception):
                    temp_path.unlink(missing_ok=True)

        except Exception as e:
            # Log error but don't fail - we'll use fallback background
            self.append_value_to_parameter("logs", f"Warning: Could not extract first frame for preview: {e}\n")

        return None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter changes, especially showing/hiding custom size fields."""
        if parameter.name == "crop_size":
            if value == "Custom":
                self.show_parameter_by_name("custom_width")
                self.show_parameter_by_name("custom_height")
            else:
                self.hide_parameter_by_name("custom_width")
                self.hide_parameter_by_name("custom_height")
            # Generate preview when size changes
            self._generate_preview()

        if parameter.name in ["custom_width", "custom_height", "crop_position"]:
            # Generate preview when custom dimensions or position change
            self._generate_preview()

        if parameter.name == "video":
            # Extract first frame when video changes
            if value:
                try:
                    # Convert to VideoUrlArtifact if needed (handles dict, VideoUrlArtifact, etc.)
                    video_artifact = to_video_artifact(value)
                    if video_artifact and hasattr(video_artifact, "value") and video_artifact.value:
                        input_url = video_artifact.value
                        # Only extract if video URL changed
                        if input_url != self._cached_video_url:
                            self._cached_first_frame = self._extract_first_frame(input_url)
                            self._cached_video_url = input_url
                    else:
                        # Clear cache if video is invalid
                        self._cached_first_frame = None
                        self._cached_video_url = None
                except Exception as e:
                    # Reset cache on error
                    self._cached_first_frame = None
                    self._cached_video_url = None
                    # Log error for debugging
                    self.append_value_to_parameter("logs", f"Warning: Could not process video for preview: {e}\n")
            else:
                # Clear cache if video is removed
                self._cached_first_frame = None
                self._cached_video_url = None

            # Generate preview when video is set
            self._generate_preview()

        return super().after_value_set(parameter, value)

    def _get_crop_dimensions(self) -> tuple[int, int] | None:
        """Get the target crop dimensions."""
        crop_size = self.get_parameter_value("crop_size") or "1K (1024x1024)"

        if crop_size == "Custom":
            width = self.get_parameter_value("custom_width") or 1024
            height = self.get_parameter_value("custom_height") or 1024
            if width > 0 and height > 0:
                return (width, height)
            return None

        # Try to parse from preset
        if crop_size in RESOLUTION_PRESETS:
            dimensions = RESOLUTION_PRESETS[crop_size]
            if dimensions != (0, 0):  # Not the Custom placeholder
                return dimensions

        # Try to parse as string
        parsed = parse_size_string(crop_size)
        return parsed

    def _calculate_crop_coordinates(
        self, video_width: int, video_height: int, crop_width: int, crop_height: int
    ) -> tuple[int, int]:
        """Calculate crop starting coordinates based on position setting."""
        position = self.get_parameter_value("crop_position") or "center"

        if position == "center":
            x = (video_width - crop_width) // 2
            y = (video_height - crop_height) // 2
        elif position == "top-left":
            x = 0
            y = 0
        elif position == "top-right":
            x = video_width - crop_width
            y = 0
        elif position == "bottom-left":
            x = 0
            y = video_height - crop_height
        elif position == "bottom-right":
            x = video_width - crop_width
            y = video_height - crop_height
        elif position == "top-center":
            x = (video_width - crop_width) // 2
            y = 0
        elif position == "bottom-center":
            x = (video_width - crop_width) // 2
            y = video_height - crop_height
        elif position == "left-center":
            x = 0
            y = (video_height - crop_height) // 2
        elif position == "right-center":
            x = video_width - crop_width
            y = (video_height - crop_height) // 2
        else:
            # Default to center
            x = (video_width - crop_width) // 2
            y = (video_height - crop_height) // 2

        # Ensure coordinates are within bounds
        x = max(0, min(x, video_width - crop_width))
        y = max(0, min(y, video_height - crop_height))

        return (x, y)

    def _generate_preview(self) -> None:
        """Generate a preview image showing the crop area overlaid on the first frame."""
        # Validate video input
        video = self.parameter_values.get("video")
        if not video:
            return

        # Convert to VideoUrlArtifact if needed (handles dict, VideoUrlArtifact, etc.)
        try:
            video_artifact = to_video_artifact(video)
            if not video_artifact or not hasattr(video_artifact, "value") or not video_artifact.value:
                return
            input_url = video_artifact.value
        except Exception:
            # Can't convert video, skip preview
            return

        # Get video dimensions
        try:
            self._validate_url_safety(input_url)

            _ffmpeg_path, ffprobe_path = self._get_ffmpeg_paths()
            _, (video_width, video_height), _ = self._detect_video_properties(input_url, ffprobe_path)
        except Exception as e:
            # Can't get video dimensions, skip preview
            self.append_value_to_parameter("logs", f"Warning: Could not get video dimensions for preview: {e}\n")
            return

        # Get crop dimensions
        crop_dims = self._get_crop_dimensions()
        if not crop_dims:
            return

        crop_width, crop_height = crop_dims

        # Ensure crop dimensions don't exceed video dimensions
        crop_width = min(crop_width, video_width)
        crop_height = min(crop_height, video_height)

        # Calculate crop position
        crop_x, crop_y = self._calculate_crop_coordinates(video_width, video_height, crop_width, crop_height)

        # Scale preview to max 1920x1080 for performance while maintaining aspect ratio
        max_preview_width = 1920
        max_preview_height = 1080
        scale_factor = min(max_preview_width / video_width, max_preview_height / video_height, 1.0)

        preview_width = int(video_width * scale_factor)
        preview_height = int(video_height * scale_factor)
        preview_crop_x = int(crop_x * scale_factor)
        preview_crop_y = int(crop_y * scale_factor)
        preview_crop_width = int(crop_width * scale_factor)
        preview_crop_height = int(crop_height * scale_factor)

        # Create preview image background
        if self._cached_first_frame:
            # Use cached first frame as background, scaled to preview size
            preview_image = self._cached_first_frame.copy()
            preview_image = preview_image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        else:
            # Fallback to grey background if frame not available
            preview_image = Image.new("RGB", (preview_width, preview_height), PREVIEW_BG_COLOR)

        draw = ImageDraw.Draw(preview_image)

        # Draw white outline for original video bounds
        outline_width = max(1, int(2 * scale_factor))
        draw.rectangle(
            [(0, 0), (preview_width - 1, preview_height - 1)],
            outline=PREVIEW_BG_OUTLINE,
            width=outline_width,
        )

        # Draw cropped area overlay: semi-transparent overlay with blue outline
        # Create a semi-transparent overlay for the cropped area
        overlay = Image.new("RGBA", (preview_width, preview_height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Draw semi-transparent dark overlay outside crop area
        # First, darken everything
        overlay_draw.rectangle(
            [(0, 0), (preview_width, preview_height)],
            fill=(0, 0, 0, 128),  # Semi-transparent black
        )

        # Then clear the crop area (make it transparent so original frame shows through)
        overlay_draw.rectangle(
            [
                (preview_crop_x, preview_crop_y),
                (preview_crop_x + preview_crop_width, preview_crop_y + preview_crop_height),
            ],
            fill=(0, 0, 0, 0),  # Transparent
        )

        # Composite overlay onto preview
        preview_image = preview_image.convert("RGBA")
        preview_image = Image.alpha_composite(preview_image, overlay)
        preview_image = preview_image.convert("RGB")
        draw = ImageDraw.Draw(preview_image)

        # Draw blue outline for cropped area
        crop_outline_width = max(2, int(3 * scale_factor))
        draw.rectangle(
            [
                (preview_crop_x, preview_crop_y),
                (preview_crop_x + preview_crop_width, preview_crop_y + preview_crop_height),
            ],
            outline=PREVIEW_CROP_OUTLINE,
            width=crop_outline_width,
        )

        # Save preview image
        try:
            preview_artifact = save_pil_image_to_static_file(preview_image, "PNG")
            self.parameter_output_values["preview"] = preview_artifact
        except Exception as e:
            # Log error but don't fail the node
            self.append_value_to_parameter("logs", f"Warning: Could not generate preview: {e}\n")

    def _build_ffmpeg_command(self, input_url: str, output_path: str, input_frame_rate: float, **kwargs) -> list[str]:  # noqa: ARG002
        """Build the FFmpeg command for cropping."""
        ffmpeg_path, _ = self._get_ffmpeg_paths()

        # Get video dimensions
        _, ffprobe_path = self._get_ffmpeg_paths()
        _, (video_width, video_height), _ = self._detect_video_properties(input_url, ffprobe_path)

        # Get crop dimensions
        crop_dims = self._get_crop_dimensions()
        if not crop_dims:
            error_msg = f"{self.name}: Invalid crop dimensions"
            raise ValueError(error_msg)

        crop_width, crop_height = crop_dims

        # Validate crop dimensions
        if crop_width <= 0 or crop_height <= 0:
            error_msg = f"{self.name}: Crop dimensions must be positive, got {crop_width}x{crop_height}"
            raise ValueError(error_msg)

        # Ensure crop dimensions don't exceed video dimensions
        crop_width = min(crop_width, video_width)
        crop_height = min(crop_height, video_height)

        # Ensure crop dimensions are still positive after clamping
        if crop_width <= 0 or crop_height <= 0:
            error_msg = f"{self.name}: Crop dimensions exceed video dimensions ({video_width}x{video_height})"
            raise ValueError(error_msg)

        # Calculate crop position
        crop_x, crop_y = self._calculate_crop_coordinates(video_width, video_height, crop_width, crop_height)

        # Ensure coordinates are valid
        crop_x = max(0, min(crop_x, video_width - crop_width))
        crop_y = max(0, min(crop_y, video_height - crop_height))

        # Ensure even dimensions for video codec compatibility
        crop_width = (crop_width // 2) * 2
        crop_height = (crop_height // 2) * 2

        # Re-validate after making even
        if crop_width <= 0 or crop_height <= 0:
            error_msg = f"{self.name}: Crop dimensions too small after rounding to even numbers"
            raise ValueError(error_msg)

        # Build crop filter: crop=width:height:x:y
        crop_filter = f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}"

        # Combine with frame rate filter if needed
        video_filter = self._combine_video_filters(crop_filter, input_frame_rate)

        # Build command
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_url,
            "-vf",
            video_filter,
        ]

        # Check if video has audio
        has_audio = self._detect_audio_stream(input_url, ffprobe_path)
        if has_audio:
            cmd.extend(["-c:a", "copy"])  # Copy audio stream
        else:
            cmd.extend(["-an"])  # No audio

        # Add encoding settings based on processing speed
        preset, pixel_format, crf = self._get_processing_speed_settings()
        cmd.extend(["-preset", preset, "-pix_fmt", pixel_format, "-crf", str(crf)])

        cmd.append(output_path)

        return cmd

    def _get_custom_parameters(self) -> dict[str, Any]:
        """Get custom parameters for processing."""
        return {}

    def _get_output_suffix(self, **kwargs) -> str:  # noqa: ARG002
        """Get the output filename suffix."""
        crop_dims = self._get_crop_dimensions()
        if crop_dims:
            return f"_crop_{crop_dims[0]}x{crop_dims[1]}"
        return "_crop"

    def process(self) -> AsyncResult[None]:
        """Process the video cropping."""
        # Generate preview first
        self._generate_preview()

        # Get video input data
        input_url, detected_format = self._get_video_input_data()
        self._log_format_detection(detected_format)

        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing video crop..]\n")

        try:
            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started video cropping..]\n")
            yield lambda: self._process(input_url, detected_format)
            self.append_value_to_parameter("logs", "[Finished video cropping.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error cropping video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
