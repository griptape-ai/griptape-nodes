from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from griptape.artifacts.image_url_artifact import ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from PIL import Image

# static_ffmpeg is dynamically installed by the library loader at runtime
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

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

        # Combine frames into video or image (gif)
        try:
            if format_type == "gif":
                image_artifact = self._combine_frames_to_gif(processed_frames, frame_rate)
                self.parameter_output_values["image"] = image_artifact
                self.parameter_output_values["video"] = None
                result_details = f"Successfully combined {len(processed_frames)} frames into GIF at {frame_rate} fps"
            else:
                video_artifact = self._combine_frames_to_video(processed_frames, frame_rate, format_type)
                self.parameter_output_values["video"] = video_artifact
                self.parameter_output_values["image"] = None
                result_details = (
                    f"Successfully combined {len(processed_frames)} frames into {format_type} video at {frame_rate} fps"
                )

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

    def _get_frame_paths(self, frames_input: Any) -> list[Path]:
        """Get list of frame file paths from input (list of paths/ImageUrlArtifacts or directory path)."""
        frame_paths = []

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
        """Extract file path from various input types (str, Path, ImageUrlArtifact)."""
        if isinstance(item, str):
            # Resolve localhost URLs to workspace paths
            resolved = self._resolve_localhost_url_to_path(item)
            return Path(resolved)

        if isinstance(item, Path):
            return item

        if isinstance(item, ImageUrlArtifact):
            # Extract URL/path from ImageUrlArtifact
            url_or_path = item.value
            if not url_or_path:
                return None

            if not isinstance(url_or_path, str):
                return Path(str(url_or_path))

            # Check if it's a localhost URL - resolve to workspace path
            if url_or_path.startswith(("http://localhost:", "https://localhost:")):
                resolved_path = self._resolve_localhost_url_to_path(url_or_path)
                workspace_path = GriptapeNodes.ConfigManager().workspace_path
                full_path = workspace_path / resolved_path
                if full_path.exists():
                    return full_path
                # If resolved path doesn't exist, try as relative path
                return Path(resolved_path)

            # If it's an external URL, download it to a temp file
            if url_or_path.startswith(("http://", "https://")):
                return self._download_url_to_temp_file(url_or_path)

            # Otherwise treat as file path
            return Path(url_or_path)

        return None

    def _resolve_localhost_url_to_path(self, url: str) -> str:
        """Resolve localhost static file URLs to workspace file paths.

        Converts URLs like http://localhost:8124/workspace/static_files/file.jpg
        to actual workspace file paths like static_files/file.jpg

        Args:
            url: URL string that may be a localhost URL

        Returns:
            Resolved file path relative to workspace, or original string if not a localhost URL
        """
        if not isinstance(url, str):
            return url

        # Strip query parameters (cachebuster ?t=...)
        if "?" in url:
            url = url.split("?")[0]

        # Check if it's a localhost URL (any port)
        if url.startswith(("http://localhost:", "https://localhost:")):
            parsed = urlparse(url)
            # Extract path after /workspace/
            if "/workspace/" in parsed.path:
                workspace_relative_path = parsed.path.split("/workspace/", 1)[1]
                return workspace_relative_path

        # Not a localhost workspace URL, return as-is
        return url

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

            # Determine extension to use (use first file's extension)
            first_extension = frame_paths[0].suffix.lower()
            if not first_extension:
                first_extension = ".jpg"

            # Copy or link frames to sequential names for ffmpeg
            for idx, frame_path in enumerate(frame_paths):
                # Create sequential filename with consistent extension
                seq_filename = f"frame_{idx + 1:04d}{first_extension}"
                seq_path = temp_path / seq_filename
                shutil.copy2(frame_path, seq_path)

            # Build ffmpeg command with specific extension in pattern
            input_pattern = str(temp_path / f"frame_%04d{first_extension}")
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
        self, frame_paths: list[Path], frame_rate: float, format_type: str
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

            # Determine extension to use (use first file's extension)
            first_extension = frame_paths[0].suffix.lower()
            if not first_extension:
                first_extension = ".jpg"

            # Copy or link frames to sequential names for ffmpeg
            sequential_frames = []
            for idx, frame_path in enumerate(frame_paths):
                # Create sequential filename with consistent extension
                # ffmpeg expects pattern like frame_%04d.jpg (must match exactly)
                seq_filename = f"frame_{idx + 1:04d}{first_extension}"
                seq_path = temp_path / seq_filename

                # Copy file to temp directory
                shutil.copy2(frame_path, seq_path)
                sequential_frames.append(seq_path)

            # Build ffmpeg command with specific extension in pattern
            input_pattern = str(temp_path / f"frame_%04d{first_extension}")
            output_path = temp_path / f"output.{format_type}"

            cmd = self._build_ffmpeg_command(ffmpeg_path, input_pattern, output_path, frame_rate, format_type)

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

    def _build_ffmpeg_command(
        self, ffmpeg_path: str, input_pattern: str, output_path: Path, frame_rate: float, format_type: str
    ) -> list[str]:
        """Build ffmpeg command for combining frames."""
        cmd = [
            ffmpeg_path,
            "-framerate",
            str(frame_rate),
            "-i",
            input_pattern,
        ]

        if format_type == "gif":
            # GIF requires special handling with palette
            # First pass: generate palette
            palette_path = output_path.parent / "palette.png"
            palette_cmd = [
                ffmpeg_path,
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

        cmd.extend(["-y", str(output_path)])
        return cmd

    def _set_safe_defaults(self) -> None:
        """Set safe default output values on failure."""
        self.parameter_output_values["video"] = None
        self.parameter_output_values["image"] = None
        self.parameter_output_values["image"] = None
