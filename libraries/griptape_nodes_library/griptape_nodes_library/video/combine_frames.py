from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from griptape.artifacts.audio_url_artifact import AudioUrlArtifact
from griptape.artifacts.image_url_artifact import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image

# static_ffmpeg is dynamically installed by the library loader at runtime
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.utils.artifact_normalization import _resolve_file_path

logger = logging.getLogger("griptape_nodes")

__all__ = ["CombineFrames"]

# Constants
ORDERING_MODES = ["Sequential", "Respect frame numbers"]
FORMAT_OPTIONS = ["mp4", "mov", "gif"]
DEFAULT_FRAME_RATE = 30.0
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class CombineFrames(SuccessFailureNode):
    """Combine image frames into a video using ffmpeg.

    Inputs:
        - frames_input (list[str] | str): List of file paths OR directory path containing frames
        - frame_rate (float): Output frame rate in fps (default: 30.0)
        - ordering_mode (str): "Sequential" (1 frame per image) or "Respect frame numbers" (gaps indicate holds)
        - format (str): Output video format - mp4, mov, or gif
        - audio (AudioUrlArtifact | str, optional): Optional audio file to add to video (only applies to mp4/mov, not GIF)

    Outputs:
        - video (VideoUrlArtifact): Combined video output
        - was_successful (bool): Whether the combination succeeded
        - result_details (str): Details about the combination result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES

        # Frames input - can be list of paths, ImageUrlArtifacts, or directory path
        self.add_parameter(
            Parameter(
                name="frames_input",
                input_types=["list", "str", "ImageUrlArtifact"],
                type="str",
                tooltip="List of frame file paths, ImageUrlArtifacts, OR directory path containing frames",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "frames or directory"},
            )
        )

        # Frame rate parameter
        self.add_parameter(
            ParameterFloat(
                name="frame_rate",
                default_value=DEFAULT_FRAME_RATE,
                tooltip="Output frame rate in fps",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Ordering mode dropdown
        self.add_parameter(
            ParameterString(
                name="ordering_mode",
                default_value=ORDERING_MODES[0],
                tooltip="Sequential: 1 frame per image. Respect frame numbers: gaps in frame numbers indicate holds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=ORDERING_MODES)},
            )
        )

        # Format dropdown
        self.add_parameter(
            ParameterString(
                name="format",
                default_value=FORMAT_OPTIONS[0],
                tooltip="Output video format",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=FORMAT_OPTIONS)},
            )
        )

        # Audio input (optional) - only applies to mp4/mov formats
        self.add_parameter(
            ParameterAudio(
                name="audio",
                default_value="",
                tooltip="Optional audio file to add to the video (only applies to mp4/mov formats, not GIF)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Combined video output (mp4/mov)",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Image output (hidden by default, shown when format is gif)
        self.add_parameter(
            Parameter(
                name="image",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="Combined GIF output",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
                hide=True,
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the frame combination result or any errors",
            result_details_placeholder="Combination status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to update dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "format":
            if value == "gif":
                self.show_parameter_by_name("image")
                self.hide_parameter_by_name("video")
            else:
                self.hide_parameter_by_name("image")
                self.show_parameter_by_name("video")

    def process(self) -> None:
        """Process method to combine frames into video."""
        self._clear_execution_status()
        logger.info("%s starting frame combination", self.name)

        # Get parameters
        frames_input = self.get_parameter_value("frames_input")
        frame_rate = self.get_parameter_value("frame_rate") or DEFAULT_FRAME_RATE
        ordering_mode = self.get_parameter_value("ordering_mode") or ORDERING_MODES[0]
        format_type = self.get_parameter_value("format") or FORMAT_OPTIONS[0]

        # Validate inputs
        if not frames_input:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires frames input (list of paths or directory path)."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no frames input", self.name)
            return

        if frame_rate <= 0:
            self._set_safe_defaults()
            error_msg = f"{self.name}: Frame rate must be greater than 0 (got {frame_rate})"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid frame rate", self.name)
            return

        # Get frame file paths
        frame_paths = self._get_frame_paths(frames_input)
        if not frame_paths:
            self._set_safe_defaults()
            error_msg = f"{self.name}: No valid frame files found in input"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no frame files", self.name)
            return

        # Process frames based on ordering mode
        if ordering_mode == "Respect frame numbers":
            processed_frames = self._process_respect_frame_numbers(frame_paths)
        else:
            processed_frames = frame_paths

        if not processed_frames:
            self._set_safe_defaults()
            error_msg = f"{self.name}: No frames to combine after processing"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no processed frames", self.name)
            return

        # Get audio input (optional, only used for mp4/mov)
        audio_input = self.get_parameter_value("audio")

        # Combine frames into video or image (gif)
        try:
            if format_type == "gif":
                image_artifact = self._combine_frames_to_gif(processed_frames, frame_rate)
                self.parameter_output_values["image"] = image_artifact
                self.parameter_output_values["video"] = None
                result_details = f"Successfully combined {len(processed_frames)} frames into GIF at {frame_rate} fps"
            else:
                video_artifact = self._combine_frames_to_video(processed_frames, frame_rate, format_type, audio_input)
                self.parameter_output_values["video"] = video_artifact
                self.parameter_output_values["image"] = None
                audio_note = " with audio" if audio_input else ""
                result_details = f"Successfully combined {len(processed_frames)} frames into {format_type} video at {frame_rate} fps{audio_note}"

            self._set_status_results(was_successful=True, result_details=result_details)
            logger.info("%s combined %d frames successfully", self.name, len(processed_frames))

        except Exception as e:
            self._set_safe_defaults()
            error_msg = f"{self.name} failed to combine frames: {e}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s combination failed: %s", self.name, e)
            self._handle_failure_exception(RuntimeError(error_msg))

    def _validate_image_file(self, image_path: Path) -> bool:
        """Validate that an image file is readable and not corrupted."""
        if not image_path.exists() or not image_path.is_file():
            return False

        if image_path.stat().st_size == 0:
            logger.warning("%s skipping empty image file: %s", self.name, image_path)
            return False

        try:
            # Try to open and verify the image
            with Image.open(image_path) as img:
                img.verify()  # Verify that it's a valid image
            return True
        except Exception as e:
            logger.warning("%s skipping invalid/corrupted image file %s: %s", self.name, image_path, e)
            return False

    def _detect_image_format(self, image_path: Path) -> tuple[str, str]:
        """Detect the actual image format and return (format_name, extension).

        Args:
            image_path: Path to the image file

        Returns:
            Tuple of (format_name, extension) e.g., ("PNG", ".png")
            Falls back to ("PNG", ".png") if detection fails
        """
        if not image_path.exists():
            return ("PNG", ".png")

        try:
            with Image.open(image_path) as img:
                actual_format = img.format
                if actual_format:
                    # Map PIL format names to extensions
                    format_to_ext = {
                        "PNG": ".png",
                        "JPEG": ".jpg",
                        "JPG": ".jpg",
                        "WEBP": ".webp",
                        "GIF": ".gif",
                        "BMP": ".bmp",
                        "TIFF": ".tiff",
                        "TIF": ".tiff",
                    }
                    ext = format_to_ext.get(actual_format.upper(), ".png")
                    return (actual_format.upper(), ext)
        except Exception as e:
            logger.warning("%s failed to detect format for %s: %s", self.name, image_path, e)

        # Default fallback
        return ("PNG", ".png")

    def _normalize_image_for_ffmpeg(self, image_path: Path, output_path: Path, target_format: str) -> None:
        """Normalize an image for FFmpeg by converting to RGB and saving in target format.

        Args:
            image_path: Source image path
            output_path: Destination path with correct extension
            target_format: Target format name (e.g., "PNG", "JPEG")
        """
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for formats like RGBA, LA, P, etc.)
            if img.mode in ("RGBA", "LA", "P"):
                # Create RGB background
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = rgb_img
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Save in target format
            save_kwargs = {}
            if target_format == "JPEG" or target_format == "WEBP":
                save_kwargs["quality"] = 95

            img.save(output_path, target_format, **save_kwargs)

    def _get_frame_paths(self, frames_input: Any) -> list[Path]:
        """Get list of frame file paths from input (list of paths/ImageUrlArtifacts or directory path)."""
        frame_paths = []

        # Handle case where list is passed as a string (e.g., serialized list)
        if isinstance(frames_input, str):
            # Check if it looks like a list representation
            stripped = frames_input.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    # Try to parse as JSON first
                    parsed = json.loads(frames_input)
                    if isinstance(parsed, list):
                        frames_input = parsed
                    else:
                        # If JSON parsing gives non-list, try ast.literal_eval
                        frames_input = ast.literal_eval(frames_input)
                except (json.JSONDecodeError, ValueError, SyntaxError):
                    # If JSON parsing fails, try ast.literal_eval as fallback
                    try:
                        frames_input = ast.literal_eval(frames_input)
                    except (ValueError, SyntaxError) as e:
                        logger.warning("%s failed to parse list string '%s...': %s", self.name, frames_input[:100], e)
                        # Fall through to treat as directory path string

        if isinstance(frames_input, list):
            # Input is a list of file paths or ImageUrlArtifacts
            for item in frames_input:
                path = self._extract_path_from_item(item)
                if path and path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    if self._validate_image_file(path):
                        frame_paths.append(path)

        elif isinstance(frames_input, str):
            # Input is a directory path
            input_path = Path(frames_input)
            if not input_path.exists():
                return []

            if input_path.is_file():
                # Single file
                if input_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    if self._validate_image_file(input_path):
                        frame_paths.append(input_path)
            elif input_path.is_dir():
                # Directory - find all image files
                for ext in SUPPORTED_IMAGE_EXTENSIONS:
                    found_paths = list(input_path.glob(f"*{ext}"))
                    found_paths.extend(input_path.glob(f"*{ext.upper()}"))
                    # Validate each found image
                    for found_path in found_paths:
                        if self._validate_image_file(found_path):
                            frame_paths.append(found_path)

        elif isinstance(frames_input, ImageUrlArtifact):
            # Single ImageUrlArtifact
            path = self._extract_path_from_item(frames_input)
            if path and path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                if self._validate_image_file(path):
                    frame_paths.append(path)

        # Sort by filename for consistent ordering
        frame_paths.sort(key=lambda p: p.name)
        return frame_paths

    def _extract_path_from_item(self, item: Any) -> Path | None:
        """Extract file path from various input types (str, Path, ImageUrlArtifact).

        Uses _resolve_file_path from artifact_normalization to handle localhost URL resolution.
        """
        if isinstance(item, Path):
            return item

        # Extract URL/path string from various input types
        url_or_path = None

        if isinstance(item, str):
            url_or_path = item

        elif isinstance(item, ImageUrlArtifact):
            url_or_path = item.value
            if not url_or_path:
                return None
            if not isinstance(url_or_path, str):
                return Path(str(url_or_path))

        else:
            return None

        # If it's an external URL (not localhost), download it to a temp file
        if isinstance(url_or_path, str) and url_or_path.startswith(("http://", "https://")):
            if not url_or_path.startswith(("http://localhost:", "https://localhost:")):
                return self._download_url_to_temp_file(url_or_path)

        # Use _resolve_file_path to handle localhost URLs and path resolution
        resolved_path = _resolve_file_path(url_or_path)
        if resolved_path:
            return resolved_path

        # Fallback: try as direct path
        return Path(url_or_path) if url_or_path else None

    def _download_url_to_temp_file(self, url: str) -> Path | None:
        """Download image from URL to temporary file."""
        try:
            # Create temp file with appropriate extension
            # Try to determine extension from URL or default to .jpg
            ext = ".jpg"
            for supported_ext in SUPPORTED_IMAGE_EXTENSIONS:
                if supported_ext in url.lower():
                    ext = supported_ext
                    break

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                temp_path = Path(temp_file.name)

            # Download the image
            with httpx.Client(timeout=60) as client:
                response = client.get(url)
                response.raise_for_status()
                temp_path.write_bytes(response.content)

            logger.debug("%s downloaded image from URL to temp file: %s", self.name, temp_path)
            return temp_path

        except Exception as e:
            logger.warning("%s failed to download image from URL %s: %s", self.name, url, e)
            return None

    def _process_respect_frame_numbers(self, frame_paths: list[Path]) -> list[Path]:
        """Process frames respecting frame numbers, duplicating to fill gaps."""
        if not frame_paths:
            return []

        # Parse frame numbers from filenames
        frame_data = []
        for frame_path in frame_paths:
            frame_num = self._extract_frame_number_from_filename(frame_path.name)
            if frame_num is not None:
                frame_data.append((frame_num, frame_path))

        if not frame_data:
            # No frame numbers found, return original list
            return frame_paths

        # Sort by frame number
        frame_data.sort(key=lambda x: x[0])

        # Build sequence with duplicates to fill gaps
        processed_frames = []
        for idx, (frame_num, frame_path) in enumerate(frame_data):
            processed_frames.append(frame_path)

            # Check if there's a gap before next frame
            if idx < len(frame_data) - 1:
                next_frame_num = frame_data[idx + 1][0]
                gap = next_frame_num - frame_num

                # If gap > 1, duplicate current frame to fill gap
                if gap > 1:
                    processed_frames.extend([frame_path] * (gap - 1))

        return processed_frames

    def _extract_frame_number_from_filename(self, filename: str) -> int | None:
        """Extract frame number from filename (e.g., extract.0001.jpg -> 1)."""
        # Try to find 4-digit number pattern
        match = re.search(r"(\d{4,})", filename)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        # Try to find any number sequence
        match = re.search(r"(\d+)", filename)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        return None

    def _combine_frames_to_gif(self, frame_paths: list[Path], frame_rate: float) -> ImageUrlArtifact:
        """Combine frames into GIF using ffmpeg, returning ImageUrlArtifact."""
        if not frame_paths:
            error_msg = "No frames to combine"
            raise ValueError(error_msg)

        try:
            ffmpeg_path, _ = run.get_or_fetch_platform_executables_else_raise()
        except Exception as e:
            error_msg = f"FFmpeg not found: {e}"
            raise ValueError(error_msg) from e

        # Create temporary directory for sequential frame files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Detect format from first frame (assume all frames are same format)
            detected_format, detected_ext = self._detect_image_format(frame_paths[0])
            logger.debug("%s detected image format: %s (extension: %s)", self.name, detected_format, detected_ext)

            # Normalize all frames to detected format with correct extension
            # This handles cases where files have wrong extensions (e.g., .jpg but are actually PNG)
            for idx, frame_path in enumerate(frame_paths):
                # Create sequential filename with detected extension (start from 0 to match FFmpeg pattern)
                seq_filename = f"frame_{idx:04d}{detected_ext}"
                seq_path = temp_path / seq_filename

                # Normalize image format (convert to RGB, save in detected format)
                try:
                    self._normalize_image_for_ffmpeg(frame_path, seq_path, detected_format)
                except Exception as e:
                    error_msg = f"Failed to normalize frame {frame_path}: {e}"
                    raise RuntimeError(error_msg) from e

            # Build ffmpeg command with detected extension in pattern
            input_pattern = str(temp_path / f"frame_%04d{detected_ext}")
            output_path = temp_path / "output.gif"

            cmd = self._build_ffmpeg_command(ffmpeg_path, input_pattern, output_path, frame_rate, "gif")

            # Run ffmpeg
            try:
                subprocess.run(  # noqa: S603
                    cmd, capture_output=True, text=True, check=True, timeout=300
                )
            except subprocess.TimeoutExpired as e:
                error_msg = f"FFmpeg timed out combining frames: {e}"
                raise RuntimeError(error_msg) from e
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed to combine frames: {e.stderr}"
                raise RuntimeError(error_msg) from e

            # Read output GIF
            if not output_path.exists():
                error_msg = "FFmpeg did not create output GIF file"
                raise RuntimeError(error_msg)

            gif_bytes = output_path.read_bytes()

            # Save to static storage as ImageUrlArtifact
            static_files_manager = GriptapeNodes.StaticFilesManager()
            filename = f"combined_frames_{len(frame_paths)}frames_{frame_rate}fps.gif"
            saved_url = static_files_manager.save_static_file(gif_bytes, filename)

            return ImageUrlArtifact(value=saved_url, name=filename)

    def _combine_frames_to_video(
        self, frame_paths: list[Path], frame_rate: float, format_type: str, audio_input: Any = None
    ) -> VideoUrlArtifact:
        """Combine frames into video using ffmpeg."""
        if not frame_paths:
            error_msg = "No frames to combine"
            raise ValueError(error_msg)

        try:
            ffmpeg_path, _ = run.get_or_fetch_platform_executables_else_raise()
        except Exception as e:
            error_msg = f"FFmpeg not found: {e}"
            raise ValueError(error_msg) from e

        # Create temporary directory for sequential frame files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Detect format from first frame (assume all frames are same format)
            detected_format, detected_ext = self._detect_image_format(frame_paths[0])
            logger.debug("%s detected image format: %s (extension: %s)", self.name, detected_format, detected_ext)

            # Normalize all frames to detected format with correct extension
            # This handles cases where files have wrong extensions (e.g., .jpg but are actually PNG)
            sequential_frames = []
            for idx, frame_path in enumerate(frame_paths):
                # Create sequential filename with detected extension (start from 0 to match FFmpeg pattern)
                seq_filename = f"frame_{idx:04d}{detected_ext}"
                seq_path = temp_path / seq_filename

                # Normalize image format (convert to RGB, save in detected format)
                try:
                    self._normalize_image_for_ffmpeg(frame_path, seq_path, detected_format)
                    sequential_frames.append(seq_path)
                except Exception as e:
                    error_msg = f"Failed to normalize frame {frame_path}: {e}"
                    raise RuntimeError(error_msg) from e

            # Build ffmpeg command with detected extension in pattern
            input_pattern = str(temp_path / f"frame_%04d{detected_ext}")
            output_path = temp_path / f"output.{format_type}"

            # Extract audio URL if provided
            audio_url = self._extract_audio_url(audio_input)

            cmd = self._build_ffmpeg_command(
                ffmpeg_path, input_pattern, output_path, frame_rate, format_type, audio_url
            )

            # Run ffmpeg
            try:
                subprocess.run(  # noqa: S603
                    cmd, capture_output=True, text=True, check=True, timeout=300
                )
            except subprocess.TimeoutExpired as e:
                error_msg = f"FFmpeg timed out combining frames: {e}"
                raise RuntimeError(error_msg) from e
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed to combine frames: {e.stderr}"
                raise RuntimeError(error_msg) from e

            # Read output video
            if not output_path.exists():
                error_msg = "FFmpeg did not create output video file"
                raise RuntimeError(error_msg)

            video_bytes = output_path.read_bytes()

            # Save to static storage
            static_files_manager = GriptapeNodes.StaticFilesManager()
            filename = f"combined_frames_{len(frame_paths)}frames_{frame_rate}fps.{format_type}"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)

            return VideoUrlArtifact(value=saved_url, name=filename)

    def _extract_audio_url(self, audio_input: Any) -> str | None:
        """Extract audio URL from audio input (AudioUrlArtifact, string, etc.).

        Args:
            audio_input: Audio input (AudioUrlArtifact, string URL, or None)

        Returns:
            Absolute audio file path if found, None otherwise
        """
        if not audio_input:
            return None

        audio_url = None

        if isinstance(audio_input, AudioUrlArtifact):
            audio_url = audio_input.value
            if not isinstance(audio_url, str):
                return None

        elif isinstance(audio_input, str):
            audio_url = audio_input

        elif isinstance(audio_input, dict) and "value" in audio_input:
            audio_url = str(audio_input.get("value", ""))

        elif hasattr(audio_input, "value"):
            try:
                audio_value = getattr(audio_input, "value", None)
                if audio_value:
                    audio_url = str(audio_value)
            except (AttributeError, TypeError):
                pass

        if not audio_url:
            return None

        # Use _resolve_file_path to handle localhost URLs and path resolution
        resolved_path = _resolve_file_path(audio_url)
        if resolved_path:
            return str(resolved_path)

        # If _resolve_file_path returned None, might be an external URL - return as-is
        return audio_url

    def _build_ffmpeg_command(
        self,
        ffmpeg_path: str,
        input_pattern: str,
        output_path: Path,
        frame_rate: float,
        format_type: str,
        audio_url: str | None = None,
    ) -> list[str]:
        """Build ffmpeg command for combining frames.

        Args:
            ffmpeg_path: Path to ffmpeg executable
            input_pattern: Pattern for input frames (e.g., "frame_%04d.png")
            output_path: Output video file path
            frame_rate: Frame rate for the video
            format_type: Output format (mp4, mov, gif)
            audio_url: Optional audio file URL/path to add to video
        """
        cmd = [
            ffmpeg_path,
            "-f",
            "image2",
            "-framerate",
            str(frame_rate),
            "-i",
            input_pattern,
        ]

        # Add audio input if provided (only for mp4/mov, not GIF)
        if audio_url and format_type in ("mp4", "mov"):
            cmd.extend(["-i", audio_url])

        if format_type == "gif":
            # GIF requires special handling with palette
            # First pass: generate palette
            palette_path = output_path.parent / "palette.png"
            palette_cmd = [
                ffmpeg_path,
                "-f",
                "image2",
                "-framerate",
                str(frame_rate),
                "-i",
                input_pattern,
                "-vf",
                "fps=10,scale=320:-1:flags=lanczos,palettegen",
                "-y",
                str(palette_path),
            ]

            # Run palette generation
            try:
                subprocess.run(palette_cmd, capture_output=True, text=True, check=True, timeout=60)  # noqa: S603
            except subprocess.CalledProcessError as e:
                logger.warning("%s palette generation failed, using simple GIF: %s", self.name, e.stderr)
                # Fallback to simple GIF without palette
                cmd.extend(["-vf", "fps=10,scale=320:-1"])
            else:
                # Second pass: use palette
                cmd = [
                    ffmpeg_path,
                    "-f",
                    "image2",
                    "-framerate",
                    str(frame_rate),
                    "-i",
                    input_pattern,
                    "-i",
                    str(palette_path),
                    "-lavfi",
                    "fps=10,scale=320:-1:flags=lanczos[x];[x][1:v]paletteuse",
                ]

        elif format_type in ("mp4", "mov"):
            # MP4/MOV use H.264 codec
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                ]
            )

            # Add audio handling if audio is provided
            if audio_url:
                # Map audio stream and encode with AAC codec
                cmd.extend(
                    [
                        "-map",
                        "0:v",  # Map video from first input (frames)
                        "-map",
                        "1:a",  # Map audio from second input (audio file)
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-shortest",  # End when shortest input ends (sync audio to video length)
                    ]
                )
            else:
                # No audio - explicitly disable audio
                cmd.append("-an")

        cmd.extend(["-y", str(output_path)])
        return cmd

    def _set_safe_defaults(self) -> None:
        """Set safe default output values on failure."""
        self.parameter_output_values["video"] = None
        self.parameter_output_values["image"] = None
        self.parameter_output_values["image"] = None
