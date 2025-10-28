import json
import subprocess
from dataclasses import dataclass
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


@dataclass
class FileDetails:
    """File-level metadata with guaranteed and optional fields."""

    # Guaranteed fields
    codec_name: str
    codec_type: str  # Always "video" for video streams

    # Optional fields (prefixed with optional_)
    optional_duration: float | None = None
    optional_bit_rate: int | None = None
    optional_codec_long_name: str | None = None
    optional_profile: str | None = None
    optional_level: int | None = None
    optional_pixel_format: str | None = None


@dataclass
class Dimensions:
    """Dimension-related metadata with guaranteed and optional fields."""

    # Guaranteed fields (from ffprobe)
    width: int
    height: int

    # Guaranteed fields (calculated by us)
    aspect_ratio_decimal: float
    aspect_ratio_string: str  # Either from display_aspect_ratio or calculated

    # Optional fields
    optional_coded_width: int | None = None
    optional_coded_height: int | None = None
    optional_sample_aspect_ratio: str | None = None
    optional_display_aspect_ratio: str | None = None  # Raw from ffprobe


@dataclass
class ColorDetails:
    """Color and visual quality metadata with guaranteed and optional fields."""

    # No guaranteed color fields from ffprobe

    # Optional fields
    optional_color_space: str | None = None
    optional_color_transfer: str | None = None
    optional_color_primaries: str | None = None
    optional_chroma_location: str | None = None
    optional_field_order: str | None = None


@dataclass
class FrameDetails:
    """Frame rate and timing metadata with guaranteed and optional fields."""

    # Guaranteed fields (from ffprobe)
    r_frame_rate: str  # Raw fraction string like "30/1"
    avg_frame_rate: str  # Raw fraction string
    time_base: str  # Raw fraction string

    # Guaranteed fields (calculated by us)
    frame_rate: float  # Parsed from r_frame_rate

    # Optional fields
    optional_nb_frames: int | None = None
    optional_start_time: float | None = None


@dataclass
class VideoMetadata:
    """Container for all video metadata categories."""

    file_details: FileDetails
    dimensions: Dimensions
    color_details: ColorDetails
    frame_details: FrameDetails


class GetVideoMetadata(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Input parameter
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

        # File Details Parameter Group
        with ParameterGroup(name="File Details") as file_group:
            Parameter(
                name="codec_name",
                default_value=None,
                output_type="str",
                tooltip="Video codec name (e.g., h264, vp8)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="codec_type",
                default_value=None,
                output_type="str",
                tooltip="Stream type (always 'video' for video streams)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_duration",
                default_value=None,
                output_type="float",
                tooltip="Video duration in seconds (may not be available)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_bit_rate",
                default_value=None,
                output_type="int",
                tooltip="Video bitrate (may not be available)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_codec_long_name",
                default_value=None,
                output_type="str",
                tooltip="Full codec name (may not be available)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(file_group)

        # Dimensions Parameter Group
        with ParameterGroup(name="Dimensions") as dimensions_group:
            Parameter(
                name="width",
                default_value=None,
                output_type="int",
                tooltip="Video width in pixels",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="height",
                default_value=None,
                output_type="int",
                tooltip="Video height in pixels",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="aspect_ratio_decimal",
                default_value=None,
                output_type="float",
                tooltip="Aspect ratio as decimal (width/height)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="aspect_ratio_string",
                default_value=None,
                output_type="str",
                tooltip="Aspect ratio as string (e.g., '16:9')",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_coded_width",
                default_value=None,
                output_type="int",
                tooltip="Coded width (may differ from display width)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_coded_height",
                default_value=None,
                output_type="int",
                tooltip="Coded height (may differ from display height)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(dimensions_group)

        # Color Details Parameter Group
        with ParameterGroup(name="Color Details", ui_options={"collapsed": True}) as color_group:
            Parameter(
                name="optional_color_space",
                default_value=None,
                output_type="str",
                tooltip="Color space (e.g., bt709, bt2020)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_color_transfer",
                default_value=None,
                output_type="str",
                tooltip="Color transfer characteristic",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_color_primaries",
                default_value=None,
                output_type="str",
                tooltip="Color primaries",
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(color_group)

        # Frame Details Parameter Group
        with ParameterGroup(name="Frame Details", ui_options={"collapsed": True}) as frame_group:
            Parameter(
                name="frame_rate",
                default_value=None,
                output_type="float",
                tooltip="Frame rate as decimal (e.g., 29.97)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_nb_frames",
                default_value=None,
                output_type="int",
                tooltip="Total number of frames (may not be available)",
                allowed_modes={ParameterMode.OUTPUT},
            )
            Parameter(
                name="optional_start_time",
                default_value=None,
                output_type="float",
                tooltip="Start time offset in seconds",
                allowed_modes={ParameterMode.OUTPUT},
            )
        self.add_node_element(frame_group)

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
        """Get ffprobe executable path from static-ffmpeg dependency."""
        _, ffprobe_path = run.get_or_fetch_platform_executables_else_raise()
        return ffprobe_path

    def _extract_video_metadata_structured(self, video_url: str) -> VideoMetadata:
        """Extract video metadata using ffprobe JSON output - no regex parsing!"""
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

        try:
            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=True, timeout=30
            )
        except subprocess.TimeoutExpired as e:
            msg = f"When attempting to extract video metadata, ffprobe operation timed out: {e}"
            raise ValueError(msg) from e
        except subprocess.CalledProcessError as e:
            msg = f"When attempting to extract video metadata, ffprobe failed: {e.stderr}"
            raise ValueError(msg) from e

        try:
            stream_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            msg = f"When attempting to extract video metadata, ffprobe returned invalid JSON: {e}"
            raise ValueError(msg) from e

        streams = stream_data.get("streams", [])
        if not streams:
            msg = "When attempting to extract video metadata, no video streams found in file"
            raise ValueError(msg)

        video_stream = streams[0]  # First video stream

        try:
            width = video_stream["width"]
            height = video_stream["height"]
        except KeyError as e:
            msg = f"When attempting to extract video metadata, required field missing from ffprobe output: {e}"
            raise ValueError(msg) from e

        aspect_ratio_decimal = width / height

        # Use display_aspect_ratio from ffprobe if available
        aspect_ratio_string = video_stream.get("display_aspect_ratio")
        if not aspect_ratio_string:
            aspect_ratio_string = self._calculate_aspect_ratio_string(width, height)

        # Create structured metadata from parsed data
        file_details = self._parse_file_details(video_stream)
        dimensions = self._parse_dimensions(video_stream, width, height, aspect_ratio_string, aspect_ratio_decimal)
        color_details = self._parse_color_details(video_stream)
        frame_details = self._parse_frame_details(video_stream)

        return VideoMetadata(
            file_details=file_details,
            dimensions=dimensions,
            color_details=color_details,
            frame_details=frame_details,
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

    def _parse_file_details(self, video_stream: dict) -> FileDetails:
        """Parse file-level metadata from ffprobe stream data."""
        return FileDetails(
            codec_name=video_stream["codec_name"],
            codec_type=video_stream["codec_type"],
            optional_duration=self._safe_float(video_stream.get("duration")),
            optional_bit_rate=self._safe_int(video_stream.get("bit_rate")),
            optional_codec_long_name=video_stream.get("codec_long_name"),
            optional_profile=video_stream.get("profile"),
            optional_level=self._safe_int(video_stream.get("level")),
            optional_pixel_format=video_stream.get("pix_fmt"),
        )

    def _parse_dimensions(
        self, video_stream: dict, width: int, height: int, aspect_ratio_string: str, aspect_ratio_decimal: float
    ) -> Dimensions:
        """Parse dimension-related metadata from ffprobe stream data."""
        return Dimensions(
            width=width,
            height=height,
            aspect_ratio_decimal=aspect_ratio_decimal,
            aspect_ratio_string=aspect_ratio_string,
            optional_coded_width=self._safe_int(video_stream.get("coded_width")),
            optional_coded_height=self._safe_int(video_stream.get("coded_height")),
            optional_sample_aspect_ratio=video_stream.get("sample_aspect_ratio"),
            optional_display_aspect_ratio=video_stream.get("display_aspect_ratio"),
        )

    def _parse_color_details(self, video_stream: dict) -> ColorDetails:
        """Parse color-related metadata from ffprobe stream data."""
        return ColorDetails(
            optional_color_space=video_stream.get("color_space"),
            optional_color_transfer=video_stream.get("color_transfer"),
            optional_color_primaries=video_stream.get("color_primaries"),
            optional_chroma_location=video_stream.get("chroma_location"),
            optional_field_order=video_stream.get("field_order"),
        )

    def _parse_frame_details(self, video_stream: dict) -> FrameDetails:
        """Parse frame rate and timing metadata from ffprobe stream data."""
        r_frame_rate = video_stream["r_frame_rate"]
        avg_frame_rate = video_stream["avg_frame_rate"]
        time_base = video_stream["time_base"]

        # Calculate frame rate from r_frame_rate fraction
        frame_rate = self._parse_fraction_string(r_frame_rate)

        return FrameDetails(
            r_frame_rate=r_frame_rate,
            avg_frame_rate=avg_frame_rate,
            time_base=time_base,
            frame_rate=frame_rate,
            optional_nb_frames=self._safe_int(video_stream.get("nb_frames")),
            optional_start_time=self._safe_float(video_stream.get("start_time")),
        )

    def _parse_fraction_string(self, fraction_str: str) -> float:
        """Parse ffprobe fraction string like '30/1' or '30000/1001' to float."""
        if not fraction_str or fraction_str == "0/0":
            return 0.0

        try:
            parts = fraction_str.split("/")
            expected_parts = 2
            if len(parts) == expected_parts:
                numerator = float(parts[0])
                denominator = float(parts[1])
                if denominator != 0:
                    return numerator / denominator
        except (ValueError, ZeroDivisionError):
            pass

        return 0.0

    def _safe_float(self, value: str | None) -> float | None:
        """Safely convert string to float, returning None for invalid values."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: str | None) -> int | None:
        """Safely convert string to int, returning None for invalid values."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Extract metadata when video parameter is set."""
        if parameter.name == "video":
            if not value:
                self._set_default_output_values()
            else:
                video_url = self._get_video_url(value)
                metadata = self._extract_video_metadata_structured(video_url)
                self._set_metadata_output_values(metadata)

    def _set_metadata_output_values(self, metadata: VideoMetadata) -> None:
        """Set output values from extracted metadata."""
        # File Details
        self.parameter_output_values["codec_name"] = metadata.file_details.codec_name
        self.parameter_output_values["codec_type"] = metadata.file_details.codec_type
        self.parameter_output_values["optional_duration"] = metadata.file_details.optional_duration
        self.parameter_output_values["optional_bit_rate"] = metadata.file_details.optional_bit_rate
        self.parameter_output_values["optional_codec_long_name"] = metadata.file_details.optional_codec_long_name

        # Dimensions
        self.parameter_output_values["width"] = metadata.dimensions.width
        self.parameter_output_values["height"] = metadata.dimensions.height
        self.parameter_output_values["aspect_ratio_decimal"] = metadata.dimensions.aspect_ratio_decimal
        self.parameter_output_values["aspect_ratio_string"] = metadata.dimensions.aspect_ratio_string
        self.parameter_output_values["optional_coded_width"] = metadata.dimensions.optional_coded_width
        self.parameter_output_values["optional_coded_height"] = metadata.dimensions.optional_coded_height

        # Color Details
        self.parameter_output_values["optional_color_space"] = metadata.color_details.optional_color_space
        self.parameter_output_values["optional_color_transfer"] = metadata.color_details.optional_color_transfer
        self.parameter_output_values["optional_color_primaries"] = metadata.color_details.optional_color_primaries

        # Frame Details
        self.parameter_output_values["frame_rate"] = metadata.frame_details.frame_rate
        self.parameter_output_values["optional_nb_frames"] = metadata.frame_details.optional_nb_frames
        self.parameter_output_values["optional_start_time"] = metadata.frame_details.optional_start_time

    def _set_default_output_values(self) -> None:
        """Set all output values to their defaults when no valid video input."""
        # File Details - use placeholder values for guaranteed fields
        self.parameter_output_values["codec_name"] = "unknown"
        self.parameter_output_values["codec_type"] = "video"
        self.parameter_output_values["optional_duration"] = None
        self.parameter_output_values["optional_bit_rate"] = None
        self.parameter_output_values["optional_codec_long_name"] = None

        # Dimensions - use placeholder values for guaranteed fields
        self.parameter_output_values["width"] = 0
        self.parameter_output_values["height"] = 0
        self.parameter_output_values["aspect_ratio_decimal"] = 0.0
        self.parameter_output_values["aspect_ratio_string"] = "0:0"
        self.parameter_output_values["optional_coded_width"] = None
        self.parameter_output_values["optional_coded_height"] = None

        # Color Details - all optional, set to None
        self.parameter_output_values["optional_color_space"] = None
        self.parameter_output_values["optional_color_transfer"] = None
        self.parameter_output_values["optional_color_primaries"] = None

        # Frame Details - use placeholder for guaranteed field
        self.parameter_output_values["frame_rate"] = 0.0
        self.parameter_output_values["optional_nb_frames"] = None
        self.parameter_output_values["optional_start_time"] = None

    def process(self) -> None:
        """Process method - ensures metadata extraction runs regardless of when parameter was set."""
        video_input = self.get_parameter_value("video")

        if not video_input:
            self._set_default_output_values()
        else:
            video_url = self._get_video_url(video_input)
            metadata = self._extract_video_metadata_structured(video_url)
            self._set_metadata_output_values(metadata)
