import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any

import imageio_ffmpeg

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact


@dataclass
class VideoMetadata:
    """Container for video metadata extracted from ffmpeg.

    Future fields that could be added:
    duration, fps, codec, bitrate, format, etc.
    """

    width: int
    height: int
    ratio_string: str
    ratio_decimal: float


class GetVideoMetadata(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add parameter for the video input
        self.add_parameter(
            Parameter(
                name="video",
                default_value=value,
                input_types=["VideoArtifact", "VideoUrlArtifact"],
                output_type="VideoArtifact",
                type="VideoArtifact",
                tooltip="The video to analyze for metadata",
                allowed_modes={ParameterMode.INPUT},
            )
        )

        # Add parameter for aspect ratio output (mathematical value)
        self.add_parameter(
            Parameter(
                name="ratio",
                default_value=None,
                input_types=["float"],
                output_type="float",
                type="float",
                tooltip="The aspect ratio of the video as a decimal value (width/height)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Add parameter for aspect ratio string output (human-readable)
        self.add_parameter(
            Parameter(
                name="ratio_string",
                default_value=None,
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="The aspect ratio of the video as a human-readable string (e.g., '16:9')",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _get_video_url(self, video_input: Any) -> str:
        """Extract video URL from VideoArtifact or VideoUrlArtifact."""
        if isinstance(video_input, VideoUrlArtifact):
            return video_input.value
        if hasattr(video_input, "value"):
            # Handle other artifact types that have a value attribute
            return video_input.value

        msg = f"Unsupported video input type: {type(video_input)}"
        raise ValueError(msg)

    def _get_ffprobe_exe(self) -> str:
        """Get ffprobe executable path, preferring static-ffmpeg if available."""
        try:
            # Try static-ffmpeg first (bundled ffprobe)
            from static_ffmpeg import run

            _, ffprobe_path = run.get_or_fetch_platform_executables_else_raise()
        except ImportError:
            # Fall back to system ffprobe if static-ffmpeg not available
            import shutil

            ffprobe_path = shutil.which("ffprobe")
            if not ffprobe_path:
                msg = "ffprobe not found. Install with: pip install static-ffmpeg"
                raise FileNotFoundError(msg) from None

        return ffprobe_path

    def _extract_video_metadata_structured(self, video_url: str) -> VideoMetadata:
        """Extract video metadata using ffprobe JSON output - no regex parsing!"""
        try:
            ffprobe_exe = self._get_ffprobe_exe()

            cmd = [
                ffprobe_exe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "v:0",  # Only first video stream
                video_url,
            ]

            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=True, timeout=30
            )

            # Parse JSON output - structured data, no regex!
            stream_data = json.loads(result.stdout)
            streams = stream_data.get("streams", [])

            if not streams:
                msg = "No video streams found in file"
                raise ValueError(msg)

            video_stream = streams[0]  # First video stream
            width = video_stream["width"]
            height = video_stream["height"]
            ratio_decimal = width / height

            # Use display_aspect_ratio from ffprobe if available
            ratio_string = video_stream.get("display_aspect_ratio")
            if not ratio_string:
                ratio_string = self._calculate_aspect_ratio_string(width, height)

            return VideoMetadata(
                width=width,
                height=height,
                ratio_string=ratio_string,
                ratio_decimal=ratio_decimal,
            )

        except (ImportError, FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            # Fall back to current regex-based method if ffprobe unavailable
            msg = f"Structured metadata extraction failed: {e}. Falling back to regex method."
            # Log the fallback (could use logging here)
            return self._extract_video_metadata_fallback(video_url)

    def _extract_video_metadata_fallback(self, video_url: str) -> VideoMetadata:
        """Extract video metadata using ffmpeg showinfo filter for structured output."""
        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            video_url,
            "-vf",
            "showinfo",
            "-t",
            "0.1",  # Only process 0.1 seconds to get first frame info
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=False, timeout=30
            )
        except subprocess.TimeoutExpired as e:
            msg = f"When attempting to extract video metadata, the operation timed out: {e}"
            raise ValueError(msg) from e
        except subprocess.CalledProcessError as e:
            msg = f"When attempting to extract video metadata, FFmpeg process failed: {e}"
            raise ValueError(msg) from e
        except OSError as e:
            msg = f"When attempting to extract video metadata, failed to execute FFmpeg: {e}"
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"When attempting to extract video metadata, encountered an unexpected failure: {e}"
            raise ValueError(msg) from e

        # Parse structured showinfo output from stderr
        output = result.stderr

        # Extract dimensions from showinfo structured output like "s:1920x1080"
        showinfo_dimension_match = re.search(r"s:(\d+)x(\d+)", output)
        if showinfo_dimension_match:
            width = int(showinfo_dimension_match.group(1))
            height = int(showinfo_dimension_match.group(2))
        else:
            # Fallback to stream info if showinfo didn't work
            stream_match = re.search(r"Stream.*Video.*?,\s*(\d+)x(\d+)", output)
            if not stream_match:
                msg = f"Could not extract video dimensions from ffmpeg output. FFmpeg stderr: {output}"
                raise ValueError(msg)
            width = int(stream_match.group(1))
            height = int(stream_match.group(2))

        ratio_decimal = width / height

        # Look for DAR (Display Aspect Ratio) in various formats
        dar_patterns = [
            r"DAR (\d+:\d+)",  # Standard DAR format
            r"\[SAR \d+:\d+ DAR (\d+:\d+)\]",  # Bracketed format with SAR
            r"aspect (\d+:\d+)",  # Alternative aspect format
        ]

        ratio_string = None
        for pattern in dar_patterns:
            dar_match = re.search(pattern, output)
            if dar_match:
                ratio_string = dar_match.group(1)
                break

        # Fallback to calculated ratio if no DAR found
        if not ratio_string:
            ratio_string = self._calculate_aspect_ratio_string(width, height)

        return VideoMetadata(
            width=width,
            height=height,
            ratio_string=ratio_string,
            ratio_decimal=ratio_decimal,
        )

    def _calculate_aspect_ratio_string(self, width: int, height: int) -> str:
        """Calculate simplified aspect ratio string from width and height."""

        # Calculate GCD to simplify the ratio
        def gcd(a: int, b: int) -> int:
            while b:
                a, b = b, a % b
            return a

        divisor = gcd(width, height)
        simplified_width = width // divisor
        simplified_height = height // divisor

        return f"{simplified_width}:{simplified_height}"

    def process(self) -> None:
        video_input = self.get_parameter_value("video")

        if video_input is None:
            msg = "No video input provided"
            raise ValueError(msg)

        video_url = self._get_video_url(video_input)

        # Try structured ffprobe approach first, fallback to regex if needed
        metadata = self._extract_video_metadata_structured(video_url)

        # Set output values (happy path at end)
        self.parameter_output_values["ratio"] = metadata.ratio_decimal
        self.parameter_output_values["ratio_string"] = metadata.ratio_string
