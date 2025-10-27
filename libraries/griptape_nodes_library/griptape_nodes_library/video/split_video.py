import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# static_ffmpeg is dynamically installed by the library loader at runtime
# into the library's own virtual environment, but not available during type checking
import static_ffmpeg.run  # type: ignore[import-untyped]
from griptape.artifacts.video_url_artifact import VideoUrlArtifact
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape.structures import Agent as GriptapeAgent
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.video_utils import (
    detect_video_format,
    sanitize_filename,
    seconds_to_ts,
    smpte_to_seconds,
    to_video_artifact,
    validate_url,
)

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
MODEL = "gpt-4.1-mini"

# Constants
TIMECODE_SEGMENT_PARTS = 2
FRAME_RATE_TOLERANCE = 0.1
MIN_SEGMENT_DURATION_FOR_STREAM_COPY = 2.0  # seconds
MIN_VIDEO_FILE_SIZE = 1024  # bytes
VIDEO_DURATION_BUFFER = 0.1  # seconds - small buffer to avoid keyframe issues


# ----------------------------
# Input parsing
# ----------------------------


@dataclass
class Segment:
    start_sec: float
    end_sec: float
    title: str
    raw_id: str | None = None


# ----------------------------
# Command generation / execution
# ----------------------------


@dataclass
class FfmpegConfig:
    """Configuration for FFmpeg command generation."""

    stream_copy: bool = True
    accurate_seek: bool = True
    keep_all_streams: bool = True


def build_ffmpeg_cmd(
    input_path: str,
    seg: Segment,
    outdir: str,
    config: FfmpegConfig,
) -> list[str]:
    """Return a single ffmpeg command as a list (safe for subprocess).

    - stream_copy=True uses -c copy (fast, keyframe-aligned)
    - accurate_seek=True places -ss/-to AFTER -i (decode-based seek, more accurate)
    - keep_all_streams=True adds -map 0 to keep audio/subs/timecode.
    """
    Path(outdir).mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(seg.title)
    out_path = Path(outdir) / f"{base}.mp4"

    ss = seconds_to_ts(seg.start_sec)
    to = seconds_to_ts(seg.end_sec)

    # Calculate segment duration
    duration = seg.end_sec - seg.start_sec

    # For very short segments (< 2 seconds) or segments that don't start at 0,
    # use re-encoding instead of stream copy to avoid keyframe alignment issues
    use_stream_copy = config.stream_copy and duration >= MIN_SEGMENT_DURATION_FOR_STREAM_COPY and seg.start_sec == 0.0

    cmd = ["ffmpeg", "-hide_banner", "-y"]
    # accurate seek puts -ss/-to after -i; fast seek places before
    if not config.accurate_seek:
        cmd += ["-ss", ss, "-to", to, "-i", input_path]
    else:
        cmd += ["-i", input_path, "-ss", ss, "-to", to]

    if config.keep_all_streams:
        cmd += ["-map", "0"]

    if use_stream_copy:
        cmd += ["-c", "copy"]
    else:
        # Re-encode path (example: H.264 video, copy audio)
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k"]

    cmd += ["-movflags", "+faststart", str(out_path)]
    return cmd


class SplitVideo(ControlNode):
    """Split a video into multiple parts using ffmpeg."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoUrlArtifact", "VideoArtifact"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to split",
            )
        )

        # Add timecodes parameter
        timecodes_parameter = Parameter(
            name="timecodes",
            input_types=["str", "json"],
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="00:00:00:00-00:01:00:00",
            tooltip="Timecodes to split the video at. Can be JSON format or simple timecode ranges.",
            ui_options={"multiline": True, "placeholder_text": "Enter timecodes or JSON..."},
        )
        self.add_parameter(timecodes_parameter)

        # Add output videos parameter list
        self.split_videos_list = ParameterList(
            name="split_videos",
            type="VideoUrlArtifact",
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="The split video segments",
        )
        self.add_parameter(self.split_videos_list)
        # Group for logging information
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

        # Validate timecodes
        timecodes = self.parameter_values.get("timecodes")
        if not timecodes:
            msg = f"{self.name}: Timecodes parameter is required"
            exceptions.append(ValueError(msg))

        return exceptions

    def _clear_list(self) -> None:
        """Clear the parameter list."""
        self.split_videos_list.clear_list()

    def _parse_timecodes_with_agent(self, timecodes_str: str) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        if not api_key:
            error_msg = f"No API key found for {SERVICE}. Please set {API_KEY_ENV_VAR} environment variable."
            raise ValueError(error_msg)

        prompt_driver = GriptapeCloudPromptDriver(
            model=MODEL, api_key=api_key, stream=True, structured_output_strategy="tool"
        )
        agent = GriptapeAgent()
        agent.add_task(PromptTask(prompt_driver=prompt_driver))
        msg = f"""
Please parse the timecodes from the following string:
{timecodes_str}

IMPORTANT: Return ONLY the exact segments provided, with no additional segments or gap-filling.
Each line MUST include the pipe character (|) followed by "Segment X:" where X is the segment number.

Return in this EXACT format with no commentary or other text:

00:00:00:00-00:00:04:07|Segment 1:
00:00:04:08-00:00:08:15|Segment 2:

If no title is provided, just use "Segment X:" format.
"""
        try:
            response = agent.run(msg)
            self.append_value_to_parameter("logs", f"Agent response: {response}\n")
            self.append_value_to_parameter("logs", f"Agent output: {agent.output}\n")

            # The agent.output should contain the actual response text
            if hasattr(agent, "output") and agent.output:
                return str(agent.output)
            if hasattr(response, "output") and hasattr(response.output, "value"):
                return response.output.value
            error_msg = f"Unexpected agent response format: {response}"
            raise ValueError(error_msg)  # noqa: TRY301

        except Exception as e:
            error_msg = f"Agent failed to parse timecodes: {e!s}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def _parse_agent_response(self, agent_response: str, frame_rate: float, *, drop_frame: bool) -> list[Segment]:
        """Parse the agent's response string into segments."""
        segments = []
        for line_raw in agent_response.strip().split("\n"):
            line = line_raw.strip()
            if not line:
                continue

            # Try to parse format: HH:MM:SS:FF-HH:MM:SS:FF|Title
            parts = line.split("|", 1)
            if len(parts) == TIMECODE_SEGMENT_PARTS:
                time_range, title = parts
            else:
                # Fallback: if no pipe, treat the whole line as time range and generate title
                time_range = line
                title = f"Segment {len(segments) + 1}:"

            # Parse time range: HH:MM:SS:FF-HH:MM:SS:FF
            time_parts = time_range.split("-")
            if len(time_parts) != TIMECODE_SEGMENT_PARTS:
                continue

            start_tc, end_tc = time_parts

            try:
                start_sec = smpte_to_seconds(start_tc, frame_rate, drop_frame=drop_frame)
                end_sec = smpte_to_seconds(end_tc, frame_rate, drop_frame=drop_frame)

                if end_sec > start_sec:
                    segments.append(Segment(start_sec, end_sec, title.strip()))
            except Exception as e:
                self.append_value_to_parameter("logs", f"Warning: Could not parse line '{line}': {e}\n")
                continue

        return segments

    def _trim_segments_to_duration(self, segments: list[Segment], video_duration: float) -> list[Segment]:
        """Trim segments that exceed the video duration."""
        if video_duration <= 0:
            # If we can't determine duration, return segments as-is
            return segments

        trimmed_segments = []
        for i, segment in enumerate(segments):
            # If segment starts after video ends, skip it
            if segment.start_sec >= video_duration:
                self.append_value_to_parameter(
                    "logs",
                    f"Skipping segment {i + 1} '{segment.title}' - starts after video ends ({segment.start_sec:.2f}s >= {video_duration:.2f}s)\n",
                )
                continue

            # Create a copy of the segment to avoid modifying the original
            trimmed_segment = Segment(
                start_sec=segment.start_sec, end_sec=segment.end_sec, title=segment.title, raw_id=segment.raw_id
            )

            # If segment ends after video ends, trim it with a small buffer
            if trimmed_segment.end_sec > video_duration:
                original_end = trimmed_segment.end_sec
                # Use a small buffer to avoid keyframe boundary issues
                trimmed_segment.end_sec = video_duration - VIDEO_DURATION_BUFFER
                self.append_value_to_parameter(
                    "logs",
                    f"Trimming segment {i + 1} '{trimmed_segment.title}' - end time {original_end:.2f}s exceeds video duration {video_duration:.2f}s, trimming to {trimmed_segment.end_sec:.2f}s\n",
                )

            # If segment duration is too short after trimming, skip it
            if trimmed_segment.end_sec <= trimmed_segment.start_sec:
                self.append_value_to_parameter(
                    "logs",
                    f"Skipping segment {i + 1} '{trimmed_segment.title}' - duration too short after trimming ({trimmed_segment.end_sec:.2f}s <= {trimmed_segment.start_sec:.2f}s)\n",
                )
                continue

            trimmed_segments.append(trimmed_segment)

        return trimmed_segments

    def _validate_segment_bounds(self, segment: Segment, video_duration: float) -> Segment:
        """Ensure segment bounds are within video duration with safety buffer."""
        if video_duration <= 0:
            return segment

        # Create a copy to avoid modifying the original
        validated_segment = Segment(
            start_sec=segment.start_sec, end_sec=segment.end_sec, title=segment.title, raw_id=segment.raw_id
        )

        # Log original segment for debugging
        self.append_value_to_parameter(
            "logs",
            f"Validating segment '{segment.title}': {segment.start_sec:.3f}s - {segment.end_sec:.3f}s (video duration: {video_duration:.3f}s)\n",
        )

        # Ensure start time is not negative
        validated_segment.start_sec = max(0.0, validated_segment.start_sec)

        # Only trim if segment actually exceeds video duration
        if validated_segment.end_sec > video_duration:
            # Apply a small buffer only when necessary
            max_end_time = video_duration - VIDEO_DURATION_BUFFER
            self.append_value_to_parameter(
                "logs",
                f"Trimming end time from {validated_segment.end_sec:.3f}s to {max_end_time:.3f}s (exceeds video duration {video_duration:.3f}s)\n",
            )
            validated_segment.end_sec = max_end_time

        # Ensure we have a minimum duration
        if validated_segment.end_sec <= validated_segment.start_sec:
            self.append_value_to_parameter(
                "logs",
                f"Segment too short, extending end time from {validated_segment.end_sec:.3f}s to {validated_segment.start_sec + 0.1:.3f}s\n",
            )
            validated_segment.end_sec = validated_segment.start_sec + 0.1

        # Log final segment
        self.append_value_to_parameter(
            "logs",
            f"Final validated segment '{validated_segment.title}': {validated_segment.start_sec:.3f}s - {validated_segment.end_sec:.3f}s\n",
        )

        return validated_segment

    def _final_validate_segments(self, segments: list[Segment], video_duration: float) -> list[Segment]:
        """Final validation of all segments to ensure they're within bounds."""
        self.append_value_to_parameter("logs", "Final validation of segment bounds...\n")
        validated_segments = []
        for i, segment in enumerate(segments):
            validated_segment = self._validate_segment_bounds(segment, video_duration)
            if validated_segment.end_sec > validated_segment.start_sec:
                validated_segments.append(validated_segment)
                if validated_segment.start_sec != segment.start_sec or validated_segment.end_sec != segment.end_sec:
                    self.append_value_to_parameter(
                        "logs",
                        f"Adjusted segment {i + 1} bounds: {segment.start_sec:.2f}s-{segment.end_sec:.2f}s -> {validated_segment.start_sec:.2f}s-{validated_segment.end_sec:.2f}s\n",
                    )
            else:
                self.append_value_to_parameter(
                    "logs", f"Skipping segment {i + 1} after final validation - duration too short\n"
                )

        return validated_segments

    def _parse_timecodes(self, timecodes_str: str, frame_rate: float, *, drop_frame: bool) -> list[Segment]:
        """Parse timecodes using agent-based parsing."""
        try:
            # Use agent to parse timecodes
            agent_response = self._parse_timecodes_with_agent(timecodes_str)
            self.append_value_to_parameter("logs", f"Agent response: {agent_response}\n")

            # Parse agent response into segments
            segments = self._parse_agent_response(agent_response, frame_rate, drop_frame=drop_frame)

            if not segments:
                error_msg = "No valid segments found in agent response"
                raise ValueError(error_msg)  # noqa: TRY301
            return segments  # noqa: TRY300

        except Exception as e:
            error_msg = f"Error parsing timecodes with agent: {e!s}"
            raise ValueError(error_msg) from e

    def _validate_ffmpeg_paths(self) -> tuple[str, str]:
        """Validate and return FFmpeg and FFprobe paths."""
        try:
            ffmpeg_path, ffprobe_path = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
            return ffmpeg_path, ffprobe_path  # noqa: TRY300
        except Exception as e:
            error_msg = f"FFmpeg not found. Please ensure static-ffmpeg is properly installed. Error: {e!s}"
            raise ValueError(error_msg) from e

    def _detect_video_properties(self, input_url: str, ffprobe_path: str) -> tuple[float, bool, float]:
        """Detect frame rate, drop frame, and duration from video using ffprobe."""
        try:
            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                "-select_streams",
                "v:0",  # Select first video stream
                input_url,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)  # noqa: S603
            data = json.loads(result.stdout)

            if not data.get("streams"):
                return 24.0, False, 0.0  # Default fallback

            stream = data["streams"][0]
            r_frame_rate = stream.get("r_frame_rate", "24/1")

            # Parse frame rate (e.g., "30000/1001" -> 29.97)
            if "/" in r_frame_rate:
                num, den = map(int, r_frame_rate.split("/"))
                frame_rate = num / den
            else:
                frame_rate = float(r_frame_rate)

            # Determine if drop frame based on frame rate
            drop_frame = (
                abs(frame_rate - 29.97) < FRAME_RATE_TOLERANCE or abs(frame_rate - 59.94) < FRAME_RATE_TOLERANCE
            )

            # Get video duration from format or stream
            duration = 0.0
            if "format" in data and "duration" in data["format"]:
                duration = float(data["format"]["duration"])
            elif "duration" in stream:
                duration = float(stream["duration"])

            return frame_rate, drop_frame, duration  # noqa: TRY300

        except Exception as e:
            self.append_value_to_parameter("logs", f"Warning: Could not detect video properties, using defaults: {e}\n")
            return 24.0, False, 0.0  # Default fallback

    def _process_segment(
        self, segment: Segment, input_url: str, temp_dir: str, ffmpeg_path: str, config: FfmpegConfig
    ) -> str:
        """Process a single video segment."""
        duration = segment.end_sec - segment.start_sec
        self.append_value_to_parameter("logs", f"Processing segment: {segment.title} (duration: {duration:.2f}s)\n")

        # Build ffmpeg command
        cmd = build_ffmpeg_cmd(input_url, segment, temp_dir, config)

        # Replace ffmpeg with actual path
        cmd[0] = ffmpeg_path

        # Log whether we're using stream copy or re-encoding
        use_stream_copy = "-c" in cmd and "copy" in cmd
        encoding_mode = "stream copy" if use_stream_copy else "re-encoding"
        self.append_value_to_parameter("logs", f"Using {encoding_mode} for segment {segment.title}\n")
        self.append_value_to_parameter("logs", f"Segment duration: {duration:.3f}s\n")
        self.append_value_to_parameter("logs", f"Running ffmpeg command: {' '.join(cmd)}\n")

        # Run ffmpeg with timeout
        try:
            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=True, timeout=300
            )
            self.append_value_to_parameter("logs", f"FFmpeg stdout: {result.stdout}\n")
            if result.stderr:
                self.append_value_to_parameter("logs", f"FFmpeg stderr: {result.stderr}\n")
        except subprocess.TimeoutExpired as e:
            error_msg = f"FFmpeg process timed out after 5 minutes for segment {segment.title}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg error for segment {segment.title}: {e.stderr}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            self.append_value_to_parameter("logs", f"FFmpeg return code: {e.returncode}\n")
            raise ValueError(error_msg) from e

        # Find the output file
        base = sanitize_filename(segment.title)
        output_path = Path(temp_dir) / f"{base}.mp4"

        if output_path.exists():
            file_size = output_path.stat().st_size
            self.append_value_to_parameter(
                "logs", f"Successfully created segment: {output_path} (size: {file_size} bytes)\n"
            )

            # Check if file is too small (likely empty/invalid)
            if file_size < MIN_VIDEO_FILE_SIZE:  # Less than 1KB is suspicious for a video file
                error_msg = f"Output file is too small ({file_size} bytes) - likely empty or invalid: {output_path}"
                self.append_value_to_parameter("logs", f"WARNING: {error_msg}\n")
                # Don't raise error here, let it continue and see if it's actually valid

            return str(output_path)

        error_msg = f"Expected output file not found: {output_path}"
        raise ValueError(error_msg)

    def _split_video_with_ffmpeg(
        self,
        input_url: str,
        segments: list[Segment],
        *,
        stream_copy: bool = True,
        accurate_seek: bool = True,
    ) -> list[bytes]:
        """Split video using static_ffmpeg and ffmpeg."""

        def _validate_and_raise_if_invalid(url: str) -> None:
            if not validate_url(url):
                msg = f"{self.name}: Invalid or unsafe URL provided: {url}"
                raise ValueError(msg)

        try:
            # Validate URL before using in subprocess
            _validate_and_raise_if_invalid(input_url)

            # Get ffmpeg executable paths
            ffmpeg_path, _ffprobe_path = self._validate_ffmpeg_paths()

            # Create temporary directory for output files
            with tempfile.TemporaryDirectory() as temp_dir:
                output_files = []
                config = FfmpegConfig(stream_copy=stream_copy, accurate_seek=accurate_seek)

                for i, segment in enumerate(segments):
                    self.append_value_to_parameter(
                        "logs", f"Processing segment {i + 1}/{len(segments)}: {segment.title}\n"
                    )

                    output_file = self._process_segment(segment, input_url, temp_dir, ffmpeg_path, config)

                    # Read the file content before the temp directory is cleaned up
                    with Path(output_file).open("rb") as f:
                        video_bytes = f.read()
                    output_files.append(video_bytes)

                return output_files

        except Exception as e:
            error_msg = f"Error during video splitting: {e!s}"
            self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
            raise ValueError(error_msg) from e

    def _process(
        self,
        input_url: str,
        segments: list[Segment],
        *,
        stream_copy: bool,
        accurate_seek: bool,
        detected_format: str,
    ) -> None:
        """Performs the synchronous video splitting operation."""
        try:
            self.append_value_to_parameter("logs", f"Splitting video into {len(segments)} segments\n")

            # Split video using ffmpeg
            output_files = self._split_video_with_ffmpeg(
                input_url, segments, stream_copy=stream_copy, accurate_seek=accurate_seek
            )

            # Convert output files to artifacts
            split_video_artifacts = []
            original_filename = Path(input_url).stem  # Get filename without extension

            for i, video_bytes in enumerate(output_files):
                # Create filename for the split segment
                segment = segments[i]
                filename = (
                    f"{original_filename}_segment_{i + 1:03d}_{sanitize_filename(segment.title)}.{detected_format}"
                )

                # Save to static files
                url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, filename)

                # Create output artifact
                video_artifact = VideoUrlArtifact(url)
                split_video_artifacts.append(video_artifact)

                self.append_value_to_parameter("logs", f"Saved segment {i + 1}: {filename}\n")

            # Save all artifacts to parameter list
            logger.info(f"Saving {len(split_video_artifacts)} split video artifacts")
            for i, item in enumerate(split_video_artifacts):
                if i < len(self.split_videos_list):
                    current_parameter = self.split_videos_list[i]
                    self.set_parameter_value(current_parameter.name, item)
                    # Using to ensure updates are being propagated
                    self.publish_update_to_parameter(current_parameter.name, item)
                    self.parameter_output_values[current_parameter.name] = item
                    continue
                new_child = self.split_videos_list.add_child_parameter()
                # Set the parameter value
                self.set_parameter_value(new_child.name, item)

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error splitting video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e

    def process(self) -> AsyncResult[None]:
        """Executes the main logic of the node asynchronously."""
        # Clear the parameter list
        self._clear_list()

        # Get the video and timecodes
        video = self.parameter_values.get("video")
        timecodes = self.parameter_values.get("timecodes", "")

        # Initialize logs
        self.append_value_to_parameter("logs", "[Processing video split..]\n")

        try:
            # Convert to video artifact
            video_artifact = to_video_artifact(video)

            # Get the video URL directly
            input_url = video_artifact.value

            # Always detect video properties for best results
            self.append_value_to_parameter("logs", "Detecting video properties...\n")
            _ffmpeg_path, ffprobe_path = self._validate_ffmpeg_paths()
            frame_rate, drop_frame, video_duration = self._detect_video_properties(input_url, ffprobe_path)

            self.append_value_to_parameter("logs", f"Detected frame rate: {frame_rate} fps\n")
            self.append_value_to_parameter("logs", f"Detected drop frame: {drop_frame}\n")
            self.append_value_to_parameter("logs", f"Detected video duration: {video_duration:.2f} seconds\n")

            # Parse timecodes
            self.append_value_to_parameter("logs", "Parsing timecodes...\n")
            segments = self._parse_timecodes(timecodes, frame_rate, drop_frame=drop_frame)
            self.append_value_to_parameter("logs", f"Parsed {len(segments)} segments\n")

            # Trim segments that exceed video duration
            if video_duration > 0:
                self.append_value_to_parameter("logs", "Trimming segments to video duration...\n")
                original_count = len(segments)
                # Log original segments before trimming
                for i, seg in enumerate(segments):
                    self.append_value_to_parameter(
                        "logs", f"Original segment {i + 1}: {seg.start_sec:.2f}s - {seg.end_sec:.2f}s ({seg.title})\n"
                    )

                segments = self._trim_segments_to_duration(segments, video_duration)

                # Log final segments after trimming
                for i, seg in enumerate(segments):
                    self.append_value_to_parameter(
                        "logs", f"Final segment {i + 1}: {seg.start_sec:.2f}s - {seg.end_sec:.2f}s ({seg.title})\n"
                    )

                if len(segments) != original_count:
                    self.append_value_to_parameter(
                        "logs", f"Trimmed from {original_count} to {len(segments)} segments\n"
                    )

            # Check if we have any valid segments after trimming
            if not segments:
                error_msg = "No valid segments found after parsing and trimming timecodes"
                self.append_value_to_parameter("logs", f"ERROR: {error_msg}\n")
                raise ValueError(error_msg)  # noqa: TRY301

            # Final validation of all segments to ensure they're within bounds
            segments = self._final_validate_segments(segments, video_duration)

            # Detect video format for output filename
            detected_format = detect_video_format(video)
            if not detected_format:
                detected_format = "mp4"  # default fallback

            self.append_value_to_parameter("logs", f"Detected video format: {detected_format}\n")

            # Run the video processing asynchronously
            self.append_value_to_parameter("logs", "[Started video processing..]\n")
            yield lambda: self._process(
                input_url,
                segments,
                stream_copy=True,  # Always use best quality
                accurate_seek=True,  # Always use best quality
                detected_format=detected_format,
            )
            self.append_value_to_parameter("logs", "[Finished video processing.]\n")

        except Exception as e:
            error_message = str(e)
            msg = f"{self.name}: Error splitting video: {error_message}"
            self.append_value_to_parameter("logs", f"ERROR: {msg}\n")
            raise ValueError(msg) from e
