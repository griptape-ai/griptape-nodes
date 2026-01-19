from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# static_ffmpeg is dynamically installed by the library loader at runtime
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_range import ParameterRange
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["ExtractFrames"]

# Constants
EXTRACTION_MODES = ["All", "List", "Step"]
FRAME_NUMBERING_OPTIONS = ["Keep original frame numbers", "Renumber sequentially"]
FORMAT_OPTIONS = ["jpg", "png", "webp"]
DEFAULT_FILENAME_PATTERN = "extract.####.jpg"
DEFAULT_STEP = 2
MIN_FRAME_NUMBER = 0
FRAME_RANGE_LENGTH = 2
RANGE_PARTS_LENGTH = 2


class ExtractFrames(SuccessFailureNode):
    """Extract frames from a video to image files using ffmpeg.

    Inputs:
        - video (VideoUrlArtifact): Input video to extract frames from (required)
        - extraction_mode (str): How to extract frames - "All", "List", or "Step"
        - frame_range (list[float]): Frame range [start, end] to extract from
        - frame_list (str): Comma/space-separated frame numbers or ranges (e.g., "1, 2, 3, 5-8, 14 27")
        - step (int): Extract every Nth frame (default: 2)
        - output_folder (str): Folder to save extracted frames (default: relative to static files)
        - format (str): Output image format - jpg, png, or webp
        - overwrite_files (bool): Whether to overwrite existing files
        - filename_pattern (str): Filename pattern with #### for frame number (default: "extract.####.jpg")
        - frame_numbering (str): "Keep original frame numbers" or "Renumber sequentially"
        - remove_previous_frames (bool): Remove previously generated frames before extracting

    Outputs:
        - frame_paths (list[str]): List of created frame file paths
        - was_successful (bool): Whether the extraction succeeded
        - result_details (str): Details about the extraction result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES

        # Video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video to extract frames from",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "input video"},
            )
        )

        with ParameterGroup(name="Extraction Options") as extraction_options_group:
            # Extraction mode dropdown
            ParameterString(
                name="extraction_mode",
                default_value=EXTRACTION_MODES[0],
                tooltip="How to extract frames: All (all frames in range), List (specific frames), Step (every Nth frame)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=EXTRACTION_MODES)},
            )

            # Frame range selector using ParameterRange (frame-based)
            # Frame list string field (shown when mode is "List")
            ParameterString(
                name="frame_list",
                default_value="",
                tooltip='Comma or space-separated frame numbers or ranges (e.g., "1, 2, 3, 5-8, 14 27")',
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                placeholder_text="1, 2, 3, 5-8, 14 27",
                hide=True,
            )

            # Step integer field (shown when mode is "Step")
            ParameterInt(
                name="step",
                default_value=DEFAULT_STEP,
                tooltip="Extract every Nth frame (e.g., 2 = every 2nd frame)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
            )

            ParameterRange(
                name="frame_range",
                default_value=[0.0, 100.0],
                tooltip="Frame range [start, end] to extract from",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                range_slider=True,
                min_val=0.0,
                max_val=1000.0,
                step=1.0,
                min_label="start frame",
                max_label="end frame",
                hide_range_labels=False,
            )

            # Frame numbering option
            ParameterString(
                name="frame_numbering",
                default_value=FRAME_NUMBERING_OPTIONS[0],
                tooltip="Keep original frame numbers from video or renumber sequentially starting from 1",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=FRAME_NUMBERING_OPTIONS)},
            )

        self.add_node_element(extraction_options_group)

        with ParameterGroup(name="Output Options") as output_options_group:
            # Output folder parameter
            # Filename pattern
            ParameterString(
                name="filename_pattern",
                default_value=DEFAULT_FILENAME_PATTERN,
                tooltip='Filename pattern with #### for frame number (e.g., "extract.####.jpg")',
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="output_folder",
                default_value="frames",
                tooltip="Folder to save extracted frames (relative to static files location)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                placeholder_text="extracted_frames",
                traits={FileSystemPicker(allow_directories=True, allow_create=True, allow_files=False)},
            )

            # Format dropdown
            ParameterString(
                name="format",
                default_value=FORMAT_OPTIONS[0],
                tooltip="Output image format",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=FORMAT_OPTIONS)},
            )

        self.add_node_element(output_options_group)

        with ParameterGroup(name="File Options") as overwrite_options_group:
            # Overwrite files option
            ParameterBool(
                name="overwrite_files",
                default_value=True,
                tooltip="Whether to overwrite existing files",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            # Remove previous frames option
            ParameterBool(
                name="remove_previous_frames",
                default_value=False,
                tooltip="Remove previously generated frames in output folder before extracting",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(overwrite_options_group)

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="frame_paths",
                output_type="list",
                type="list",
                tooltip="List of created frame file paths",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=[],
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the frame extraction result or any errors",
            result_details_placeholder="Extraction status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to update dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "extraction_mode":
            if value == "All":
                self.hide_parameter_by_name("frame_list")
                self.hide_parameter_by_name("step")
            elif value == "List":
                self.show_parameter_by_name("frame_list")
                self.hide_parameter_by_name("step")
            elif value == "Step":
                self.hide_parameter_by_name("frame_list")
                self.show_parameter_by_name("step")
            else:
                self.hide_parameter_by_name("frame_list")
                self.hide_parameter_by_name("step")

        # Update frame_range max value when video changes
        if parameter.name == "video":
            self._update_frame_range_from_video(value)

    def _update_frame_range_from_video(self, video_input: Any) -> None:
        """Update the frame_range parameter's max value based on video frame count."""
        if not video_input:
            self._reset_frame_range_to_default()
            return

        try:
            video_url = self._extract_video_url(video_input)
            if not video_url:
                return

            frame_count = self._get_video_frame_count(video_url)
            if frame_count is None:
                logger.warning("%s could not determine video frame count, using default max", self.name)
                return

            max_frame = float(max(frame_count - 1, MIN_FRAME_NUMBER))
            self._update_frame_range_max(max_frame, frame_count)
            self.set_parameter_value("frame_range", [0, max_frame])

        except Exception as e:
            logger.warning("%s failed to update frame range from video: %s", self.name, e)

    def _reset_frame_range_to_default(self) -> None:
        """Reset frame_range parameter to default max value."""
        frame_range_param = self.get_parameter_by_name("frame_range")
        if frame_range_param and isinstance(frame_range_param, ParameterRange):
            frame_range_param.max_val = 1000.0

    def _extract_video_url(self, video_input: Any) -> str | None:
        """Extract video URL from video input."""
        if isinstance(video_input, VideoUrlArtifact):
            return video_input.value
        return str(video_input) if video_input else None

    def _update_frame_range_max(self, max_frame: float, total_frames: int) -> None:
        """Update frame_range max value and adjust current range if needed."""
        frame_range_param = self.get_parameter_by_name("frame_range")
        if not frame_range_param or not isinstance(frame_range_param, ParameterRange):
            return

        frame_range_param.max_val = max_frame
        logger.info("%s updated frame_range max to %.0f (video has %d frames)", self.name, max_frame, total_frames)

        # Adjust current range if it exceeds new max
        current_range = self.get_parameter_value("frame_range") or [0.0, 100.0]
        if isinstance(current_range, list) and len(current_range) == FRAME_RANGE_LENGTH:
            adjusted_range = self._adjust_range_to_max(current_range, max_frame)
            if adjusted_range != current_range:
                self.set_parameter_value("frame_range", adjusted_range)

    def _adjust_range_to_max(self, frame_range: list[float], max_frame: float) -> list[float]:
        """Adjust range end if it exceeds max."""
        start_frame, end_frame = frame_range
        if end_frame <= max_frame:
            return frame_range

        new_end = max_frame
        # Ensure start is not greater than end
        if start_frame > new_end:
            new_start = max(0.0, new_end - 1.0)
            return [new_start, new_end]

        return [start_frame, new_end]

    def _get_video_frame_count(self, video_url: str) -> int | None:
        """Extract video frame count using ffprobe."""
        try:
            _, ffprobe_path = run.get_or_fetch_platform_executables_else_raise()

            cmd = [
                ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "v:0",
                video_url,
            ]

            result = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, check=True, timeout=30
            )

            stream_data = json.loads(result.stdout)
            streams = stream_data.get("streams", [])
            if not streams:
                return None

            video_stream = streams[0]

            # Try to get nb_frames directly
            nb_frames_str = video_stream.get("nb_frames")
            if nb_frames_str:
                try:
                    return int(nb_frames_str)
                except (ValueError, TypeError):
                    pass

            # Calculate from duration and frame rate if nb_frames not available
            duration_str = video_stream.get("duration")
            r_frame_rate_str = video_stream.get("r_frame_rate", "30/1")

            if duration_str and r_frame_rate_str:
                try:
                    duration = float(duration_str)
                    if "/" in r_frame_rate_str:
                        num, den = map(int, r_frame_rate_str.split("/"))
                        frame_rate = num / den if den != 0 else 30.0
                    else:
                        frame_rate = float(r_frame_rate_str)

                    frame_count = int(duration * frame_rate)
                    return frame_count
                except (ValueError, TypeError, ZeroDivisionError):
                    return None

            return None

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as e:
            logger.debug("%s ffprobe failed to extract frame count: %s", self.name, e)
            return None

    def process(self) -> None:
        """Process method to extract frames from video."""
        self._clear_execution_status()
        logger.info("%s starting frame extraction", self.name)

        # Validate video input
        video = self.get_parameter_value("video")
        if not video:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires an input video for frame extraction."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no video input", self.name)
            return

        video_url = self._extract_video_url(video)
        if not video_url:
            self._set_safe_defaults()
            error_msg = f"{self.name} could not extract video URL from input."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid video URL", self.name)
            return

        # Get and validate parameters
        params = self._get_and_validate_parameters()
        if params is None:
            return

        # Extract frames
        try:
            frame_paths = self._perform_extraction(video_url, params)
            self.parameter_output_values["frame_paths"] = frame_paths
            result_details = f"Successfully extracted {len(frame_paths)} frames to {params['output_folder']}"
            self._set_status_results(was_successful=True, result_details=result_details)
            logger.info("%s extracted %d frames successfully", self.name, len(frame_paths))

        except Exception as e:
            self._set_safe_defaults()
            error_msg = f"{self.name} failed to extract frames: {e}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s extraction failed: %s", self.name, e)
            self._handle_failure_exception(RuntimeError(error_msg))

    def _get_and_validate_parameters(self) -> dict[str, Any] | None:
        """Get and validate all parameters."""
        extraction_mode = self.get_parameter_value("extraction_mode") or EXTRACTION_MODES[0]
        frame_range = self.get_parameter_value("frame_range") or [0.0, 100.0]
        frame_list_str = self.get_parameter_value("frame_list") or ""
        step = self.get_parameter_value("step") or DEFAULT_STEP
        output_folder = self.get_parameter_value("output_folder") or "frames"
        format_type = self.get_parameter_value("format") or FORMAT_OPTIONS[0]
        overwrite_files = self.get_parameter_value("overwrite_files") or False
        filename_pattern = self.get_parameter_value("filename_pattern") or DEFAULT_FILENAME_PATTERN
        frame_numbering = self.get_parameter_value("frame_numbering") or FRAME_NUMBERING_OPTIONS[0]
        remove_previous_frames = self.get_parameter_value("remove_previous_frames") or False

        # Validate frame range
        if not isinstance(frame_range, list) or len(frame_range) != FRAME_RANGE_LENGTH:
            self._set_safe_defaults()
            error_msg = f"{self.name}: Frame range must be a list with two values [start, end]"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid frame range", self.name)
            return None

        start_frame = int(frame_range[0])
        end_frame = int(frame_range[1])

        if start_frame < 0 or end_frame < start_frame:
            self._set_safe_defaults()
            error_msg = f"{self.name}: Invalid frame range - start must be >= 0 and end must be >= start"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid frame range values", self.name)
            return None

        # Determine which frames to extract
        frames_to_extract = self._determine_frames_to_extract(
            extraction_mode, frame_list_str, step, start_frame, end_frame
        )

        if not frames_to_extract:
            self._set_safe_defaults()
            error_msg = f"{self.name}: No frames to extract based on current settings"
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no frames to extract", self.name)
            return None

        return {
            "extraction_mode": extraction_mode,
            "frames_to_extract": frames_to_extract,
            "output_folder": output_folder,
            "format_type": format_type,
            "overwrite_files": overwrite_files,
            "filename_pattern": filename_pattern,
            "frame_numbering": frame_numbering,
            "remove_previous_frames": remove_previous_frames,
        }

    def _perform_extraction(self, video_url: str, params: dict[str, Any]) -> list[str]:
        """Perform the actual frame extraction."""
        # Get output directory
        output_dir = self._get_output_directory(params["output_folder"])

        # Remove previous frames if requested
        if params["remove_previous_frames"]:
            self._remove_previous_frames(output_dir, params["filename_pattern"])

        # Extract frames
        return self._extract_frames(
            video_url=video_url,
            frame_numbers=params["frames_to_extract"],
            output_dir=output_dir,
            format_type=params["format_type"],
            filename_pattern=params["filename_pattern"],
            frame_numbering=params["frame_numbering"],
            overwrite_files=params["overwrite_files"],
        )

    def _determine_frames_to_extract(
        self, extraction_mode: str, frame_list_str: str, step: int, start_frame: int, end_frame: int
    ) -> list[int]:
        """Determine which frame numbers to extract based on mode."""
        if extraction_mode == "All":
            return list(range(start_frame, end_frame + 1))

        if extraction_mode == "List":
            if not frame_list_str:
                return []

            parsed_frames = self._parse_frame_list(frame_list_str)
            # Filter to only include frames within range
            filtered_frames = [f for f in parsed_frames if start_frame <= f <= end_frame]
            return sorted(set(filtered_frames))

        if extraction_mode == "Step":
            frames = []
            current = start_frame
            while current <= end_frame:
                frames.append(current)
                current += step
            return frames

        return []

    def _parse_frame_list(self, frame_list_str: str) -> list[int]:
        """Parse frame list string with ranges and separators.

        Handles formats like: "1, 2, 3, 5-8, 14 27"
        """
        frames = []
        # Replace spaces with commas for easier parsing
        normalized = re.sub(r"\s+", ",", frame_list_str.strip())
        parts = [p.strip() for p in normalized.split(",") if p.strip()]

        for part in parts:
            if "-" in part:
                # Handle range like "5-8"
                range_parts = part.split("-", 1)
                if len(range_parts) == RANGE_PARTS_LENGTH:
                    try:
                        start = int(range_parts[0].strip())
                        end = int(range_parts[1].strip())
                        frames.extend(range(start, end + 1))
                    except (ValueError, TypeError):
                        logger.warning("%s could not parse frame range: %s", self.name, part)
                        continue
            else:
                # Handle single frame number
                try:
                    frame_num = int(part.strip())
                    frames.append(frame_num)
                except (ValueError, TypeError):
                    logger.warning("%s could not parse frame number: %s", self.name, part)
                    continue

        return frames

    def _get_output_directory(self, output_folder: str) -> Path:
        """Get output directory path, creating if needed."""
        if Path(output_folder).is_absolute():
            output_dir = Path(output_folder)
        else:
            workspace_path = GriptapeNodes.ConfigManager().workspace_path
            static_files_manager = GriptapeNodes.StaticFilesManager()
            static_files_dir = static_files_manager._get_static_files_directory()
            static_files_path = workspace_path / static_files_dir
            output_dir = static_files_path / output_folder

        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _remove_previous_frames(self, output_dir: Path, filename_pattern: str) -> None:
        """Remove previously generated frames matching the filename pattern."""
        # Convert pattern to glob pattern (replace #### with *)
        glob_pattern = filename_pattern.replace("####", "*")
        # Also handle if pattern doesn't have ####
        if "####" not in filename_pattern and "*" not in glob_pattern:
            # Try to extract base pattern
            base_name = Path(filename_pattern).stem
            glob_pattern = f"{base_name}*"

        for file_path in output_dir.glob(glob_pattern):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    logger.debug("%s removed previous frame: %s", self.name, file_path)
                except OSError as e:
                    logger.warning("%s failed to remove previous frame %s: %s", self.name, file_path, e)

    def _extract_frames(
        self,
        video_url: str,
        frame_numbers: list[int],
        output_dir: Path,
        format_type: str,
        filename_pattern: str,
        frame_numbering: str,
        *,
        overwrite_files: bool,
    ) -> list[str]:
        """Extract frames from video using ffmpeg."""
        if not frame_numbers:
            return []

        try:
            ffmpeg_path, _ = run.get_or_fetch_platform_executables_else_raise()
        except Exception as e:
            error_msg = f"FFmpeg not found: {e}"
            raise ValueError(error_msg) from e

        frame_paths = []
        renumber = frame_numbering == FRAME_NUMBERING_OPTIONS[1]

        for idx, frame_num in enumerate(frame_numbers):
            # Determine output frame number
            if renumber:
                output_frame_num = idx + 1
            else:
                output_frame_num = frame_num

            # Generate filename from pattern
            filename = filename_pattern.replace("####", f"{output_frame_num:04d}")
            # Ensure correct extension
            filename = Path(filename).with_suffix(f".{format_type}").name
            output_path = output_dir / filename

            # Skip if file exists and overwrite is disabled
            if output_path.exists() and not overwrite_files:
                logger.debug("%s skipping existing frame: %s", self.name, output_path)
                frame_paths.append(str(output_path))
                continue

            # Build ffmpeg command to extract specific frame
            # Use select filter to extract frame at specific position
            cmd = [
                ffmpeg_path,
                "-i",
                video_url,
                "-vf",
                f"select='eq(n\\,{frame_num})'",
                "-vsync",
                "0",
                "-frames:v",
                "1",
                "-y" if overwrite_files else "-n",
                str(output_path),
            ]

            try:
                subprocess.run(  # noqa: S603
                    cmd, capture_output=True, text=True, check=True, timeout=60
                )
                frame_paths.append(str(output_path))
                logger.debug("%s extracted frame %d to %s", self.name, frame_num, output_path)

            except subprocess.TimeoutExpired as e:
                error_msg = f"FFmpeg timed out extracting frame {frame_num}: {e}"
                raise RuntimeError(error_msg) from e
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed to extract frame {frame_num}: {e.stderr}"
                raise RuntimeError(error_msg) from e

        return frame_paths

    def _set_safe_defaults(self) -> None:
        """Set safe default output values on failure."""
        self.parameter_output_values["frame_paths"] = []
