from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

# static_ffmpeg is dynamically installed by the library loader at runtime
from static_ffmpeg import run  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_range import ParameterRange
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXVideoRetake"]
MAX_PROMPT_LENGTH = 5000
MAX_VIDEO_DURATION = 21
MIN_RETAKE_DURATION = 2.0
RETAKE_SEGMENT_LENGTH = 2


class LTXVideoRetake(GriptapeProxyNode):
    """Regenerate a segment of an existing video using LTX AI via Griptape Cloud model proxy.

    Inputs:
        - video (VideoUrlArtifact): Input video to edit (required, max 21s, max resolution 3840x2160, sent as base64)
        - retake_segment (list[float]): Time range [start, end] in seconds to regenerate
        - prompt (str): Text describing what should happen in the retake segment (max 5000 chars)
        - mode (str): What to replace - audio only, video only, or both (default: both)
        - model (str): Model to use (only LTX 2 Pro supported currently)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved video with retake applied
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    DEFAULT_MAX_ATTEMPTS = 240

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES

        # Model parameter (only ltx-2-pro supported)
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="LTX 2 Pro",
                tooltip="Model to use for video retake (only LTX 2 Pro supported currently)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["LTX 2 Pro"])},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text describing what should happen in the retake segment (max 5000 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe what should happen in this segment...",
                },
            )
        )

        # Video input parameter
        self.add_parameter(
            ParameterVideo(
                name="video",
                tooltip="Input video to edit (max 21 seconds, max resolution 3840x2160)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "input video"},
            )
        )

        # Time range selector using ParameterRange
        self.add_parameter(
            ParameterRange(
                name="retake_segment",
                default_value=[0.0, 2.0],
                tooltip="Time range (in seconds) of the video segment to regenerate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                range_slider=True,
                min_val=0.0,
                max_val=21.0,
                step=0.1,
                min_label="start (s)",
                max_label="end (s)",
                hide_range_labels=False,
            )
        )

        self.add_parameter(
            ParameterString(
                name="mode",
                default_value="replace_audio_and_video",
                tooltip="What to replace in the retake segment",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "replace_audio_and_video",
                            "replace_video",
                            "replace_audio",
                        ]
                    )
                },
            )
        )

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video_url",
                tooltip="Saved video with retake applied",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video retake result or any errors",
            result_details_placeholder="Retake status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to update dependent parameters."""
        super().after_value_set(parameter, value)

        # Update retake_segment max value when video changes
        if parameter.name == "video":
            self._update_segment_range_from_video(value)

    def _update_segment_range_from_video(self, video_input: Any) -> None:
        """Update the retake_segment parameter's max value based on video duration."""
        if not video_input:
            self._reset_segment_range_to_default()
            return

        try:
            video_url = self._extract_video_url(video_input)
            if not video_url:
                return

            duration = self._get_video_duration(video_url)
            if duration is None:
                logger.warning("%s could not determine video duration, using default max", self.name)
                return

            # Cap at MAX_VIDEO_DURATION (21s) as per API limits
            max_duration = min(duration, float(MAX_VIDEO_DURATION))
            self._update_segment_range_max(max_duration, duration)

        except Exception as e:
            logger.warning("%s failed to update segment range from video: %s", self.name, e)

    def _reset_segment_range_to_default(self) -> None:
        """Reset retake_segment parameter to default max value."""
        retake_segment_param = self.get_parameter_by_name("retake_segment")
        if retake_segment_param and isinstance(retake_segment_param, ParameterRange):
            retake_segment_param.max_val = float(MAX_VIDEO_DURATION)

    def _extract_video_url(self, video_input: Any) -> str | None:
        """Extract video URL from video input."""
        if isinstance(video_input, VideoUrlArtifact):
            return video_input.value
        return str(video_input) if video_input else None

    def _update_segment_range_max(self, max_duration: float, actual_duration: float) -> None:
        """Update retake_segment max value and adjust current segment if needed."""
        retake_segment_param = self.get_parameter_by_name("retake_segment")
        if not retake_segment_param or not isinstance(retake_segment_param, ParameterRange):
            return

        retake_segment_param.max_val = max_duration
        logger.info(
            "%s updated retake_segment max to %.1fs (video duration: %.1fs)", self.name, max_duration, actual_duration
        )

        # Adjust current segment if it exceeds new max
        current_segment = self.get_parameter_value("retake_segment") or [0.0, MIN_RETAKE_DURATION]
        if isinstance(current_segment, list) and len(current_segment) == RETAKE_SEGMENT_LENGTH:
            adjusted_segment = self._adjust_segment_to_max(current_segment, max_duration)
            if adjusted_segment != current_segment:
                self.set_parameter_value("retake_segment", adjusted_segment)

    def _adjust_segment_to_max(self, segment: list[float], max_duration: float) -> list[float]:
        """Adjust segment end time if it exceeds max, maintaining minimum duration."""
        start_time, end_time = segment
        if end_time <= max_duration:
            return segment

        new_end = max_duration
        # Ensure minimum duration
        if new_end - start_time < MIN_RETAKE_DURATION:
            # Try to maintain minimum by adjusting start
            new_start = max(0.0, new_end - MIN_RETAKE_DURATION)
            return [new_start, new_end]

        return [start_time, new_end]

    def _get_video_duration(self, video_url: str) -> float | None:
        """Extract video duration in seconds using ffprobe."""
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
                "v:0",  # Only first video stream
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
            duration_str = video_stream.get("duration")
            if not duration_str:
                return None

            return float(duration_str)

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as e:
            logger.debug("%s ffprobe failed to extract duration: %s", self.name, e)
            return None

    async def _process_generation(self) -> None:
        await super()._process_generation()

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "LTX 2 Pro",
            "retake_segment": self.get_parameter_value("retake_segment") or [0.0, 2.0],
            "mode": self.get_parameter_value("mode") or "replace_audio_and_video",
        }

    def _get_api_model_id(self) -> str:
        return "ltx-2-pro:retake"

    def _validate_video_input(self, video: Any) -> str | None:
        """Validate video is provided and doesn't exceed duration limits."""
        if not video:
            return f"{self.name} requires an input video for retake generation."

        video_url = self._extract_video_url(video)
        if not video_url:
            return None

        duration = self._get_video_duration(video_url)
        if duration and duration > MAX_VIDEO_DURATION:
            return (
                f"{self.name}: Input video duration ({duration:.1f}s) exceeds maximum allowed "
                f"duration of {MAX_VIDEO_DURATION}s"
            )

        return None

    def _validate_retake_segment(self, segment: list[float] | None) -> str | None:
        """Validate the retake segment time range."""
        # Validate segment structure
        if (
            not segment
            or not isinstance(segment, list)
            or len(segment) != RETAKE_SEGMENT_LENGTH
            or not isinstance(segment[0], (int, float))
            or not isinstance(segment[1], (int, float))
        ):
            return f"{self.name}: Retake segment must be a list with two numeric values [start, end]"

        start_time, end_time = segment

        # Validate time bounds - check start negative or end exceeds max
        if start_time < 0 or end_time > MAX_VIDEO_DURATION:
            if start_time < 0:
                return f"{self.name}: Start time cannot be negative (got {start_time}s)"
            return f"{self.name}: End time cannot exceed {MAX_VIDEO_DURATION}s (got {end_time}s)"

        # Validate time ordering
        if start_time >= end_time:
            return f"{self.name}: Start time must be before end time (got {segment})"

        # Validate duration
        duration = end_time - start_time
        if duration < MIN_RETAKE_DURATION:
            return (
                f"{self.name}: Retake segment must be at least {MIN_RETAKE_DURATION}s "
                f"(got {duration}s from segment {segment})"
            )

        return None

    async def _prepare_video_data_uri_async(self, video_input: Any) -> str | None:
        """Convert video input to a base64 data URI."""
        if not video_input:
            return None

        # Get the video URL from VideoUrlArtifact
        video_url = video_input.value if isinstance(video_input, VideoUrlArtifact) else str(video_input)
        if not video_url:
            return None

        if video_url.startswith("data:video/"):
            return video_url

        try:
            return await File(video_url).aread_data_uri(fallback_mime="video/mp4")
        except FileLoadError:
            logger.debug("%s failed to load video value: %s", self.name, video_url)
            return None

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for LTX Retake API."""
        params = self._get_parameters()

        video = self.get_parameter_value("video")
        video_validation_error = self._validate_video_input(video)
        if video_validation_error:
            raise ValueError(video_validation_error)

        try:
            video_data_uri = await self._prepare_video_data_uri_async(video)
        except Exception as e:
            logger.error("%s failed to process video: %s", self.name, e)
            video_data_uri = None

        if not video_data_uri:
            msg = f"{self.name} failed to process input video."
            raise ValueError(msg)

        if error := self._validate_retake_segment(params["retake_segment"]):
            raise ValueError(error)

        if len(params["prompt"]) > MAX_PROMPT_LENGTH:
            msg = (
                f"{self.name}: Prompt exceeds {MAX_PROMPT_LENGTH} characters limit "
                f"(current: {len(params['prompt'])} characters)"
            )
            raise ValueError(msg)

        # Convert [start, end] to start_time and duration
        segment = params["retake_segment"]
        start_time = float(segment[0])
        end_time = float(segment[1])
        duration = end_time - start_time

        payload: dict[str, Any] = {
            "video_uri": video_data_uri,
            "start_time": start_time,
            "duration": duration,
            "prompt": params["prompt"].strip(),
            "mode": params["mode"],
            "model": "ltx-2-pro",  # API only supports ltx-2-pro
        }

        return payload

    def _sanitize_video_uri_in_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact base64 video data from dictionary for logging."""
        sanitized = {**data}
        if "video_uri" in sanitized and isinstance(sanitized["video_uri"], str):
            video_uri = sanitized["video_uri"]
            if video_uri.startswith("data:video/"):
                parts = video_uri.split(",", 1)
                header = parts[0] if parts else "data:video/"
                b64_len = len(parts[1]) if len(parts) > 1 else 0
                sanitized["video_uri"] = f"{header},<base64 data length={b64_len}>"
        return sanitized

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        video_bytes = result_json.get("raw_bytes")
        if not isinstance(video_bytes, (bytes, bytearray)):
            msg = f"{self.name} generation completed but no video data received."
            raise TypeError(msg)

        await self._handle_completion_async(bytes(video_bytes), generation_id)

    async def _handle_completion_async(self, video_bytes: bytes, generation_id: str) -> None:
        """Handle successful completion by saving the video to static storage.

        Args:
            video_bytes: Raw binary MP4 data received from /result endpoint
            generation_id: Generation ID for filename
        """
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no video data received.",
            )
            return

        try:
            static_files_manager = GriptapeNodes.StaticFilesManager()
            filename = f"ltx_video_retake_{generation_id}.mp4"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            logger.info("%s saved video to static storage as %s", self.name, filename)
            self._set_status_results(
                was_successful=True, result_details=f"Video retake successful and saved as {filename}."
            )
        except (OSError, PermissionError) as e:
            logger.error("%s failed to save to static storage: %s", self.name, e)
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"Video generated but failed to save to storage: {e}",
            )

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:  # noqa: C901, PLR0912
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        status = str(response_json.get("status") or "").lower()
        status_detail = response_json.get("status_detail")
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")

            if details and isinstance(details, str):
                try:
                    details_obj = json.loads(details)
                    if isinstance(details_obj, dict):
                        error_obj = details_obj.get("error")
                        if isinstance(error_obj, dict):
                            clean_message = error_obj.get("message")
                            if clean_message:
                                details = clean_message
                except (ValueError, json.JSONDecodeError):
                    pass

            if error and details:
                message = f"{error}: {details}"
            elif error:
                message = error
            elif details:
                message = details
            else:
                message = f"Generation {status or 'failed'} with no details provided"

            return f"{self.name} generation {status or 'failed'}: {message}"

        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or str(error)
                return f"{self.name} request failed: {message}"
            if isinstance(error, str):
                return f"{self.name} request failed: {error}"

        return f"{self.name} generation failed.\n\nFull API response:\n{response_json}"

    def _handle_payload_build_error(self, e: Exception) -> None:
        if isinstance(e, ValueError):
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            return

        super()._handle_payload_build_error(e)

    def _handle_api_key_validation_error(self, e: ValueError) -> None:
        self._set_safe_defaults()
        self._set_status_results(was_successful=False, result_details=str(e))
        logger.error("%s API key validation failed: %s", self.name, e)

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
