from __future__ import annotations

import asyncio
import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_range import ParameterRange
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXVideoRetake"]

# Constants
HTTP_CLIENT_ERROR_STATUS = 400
MAX_PROMPT_LENGTH = 5000
MAX_VIDEO_DURATION = 21
MIN_RETAKE_DURATION = 2.0
RETAKE_SEGMENT_LENGTH = 2


class LTXVideoRetake(SuccessFailureNode):
    """Regenerate a segment of an existing video using LTX AI via Griptape Cloud model proxy.

    Inputs:
        - video (VideoUrlArtifact): Input video to edit (required, max 21s, max resolution 3840x2160)
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

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

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

        # Use PublicArtifactUrlParameter for video upload handling
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video to edit (max 21 seconds, max resolution 3840x2160)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "input video"},
            ),
            disclaimer_message="The LTX service utilizes this URL to access the video for retake generation.",
        )
        self._public_video_url_parameter.add_input_parameters()

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
                name="prompt",
                tooltip="Text describing what should happen in the retake segment (max 5000 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe what should happen in this segment...",
                },
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
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video with retake applied",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video retake result or any errors",
            result_details_placeholder="Retake status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()
        logger.info("%s starting video retake", self.name)

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            logger.error("%s API key validation failed: %s", self.name, e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Get parameters and validate
        params = self._get_parameters()
        logger.debug(
            "%s parameters: model=%s, prompt_length=%d, segment=%s, mode=%s",
            self.name,
            params["model"],
            len(params["prompt"]),
            params["retake_segment"],
            params["mode"],
        )

        # Validate video is provided
        video_uri = self._public_video_url_parameter.get_public_url_for_parameter()
        if not video_uri:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires an input video for retake generation."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no video provided", self.name)
            return

        # Validate retake segment
        validation_error = self._validate_retake_segment(params["retake_segment"])
        if validation_error:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=validation_error)
            logger.error("%s validation failed: %s", self.name, validation_error)
            return

        # Validate prompt length
        if len(params["prompt"]) > MAX_PROMPT_LENGTH:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name}: Prompt exceeds {MAX_PROMPT_LENGTH} characters limit "
                f"(current: {len(params['prompt'])} characters)"
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: prompt too long", self.name)
            return

        # Build payload with video_uri
        payload = self._build_payload(params, video_uri)

        # Submit request
        try:
            generation_id = await self._submit_request_async(payload, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result_async(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "LTX 2 Pro",
            "retake_segment": self.get_parameter_value("retake_segment") or [0.0, 2.0],
            "mode": self.get_parameter_value("mode") or "replace_audio_and_video",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

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

    async def _submit_request_async(self, payload: dict[str, Any], headers: dict[str, str]) -> str:
        model_id_with_modality = "ltx-2-pro:retake"
        post_url = urljoin(self._proxy_base, f"models/{model_id_with_modality}")

        logger.info("Submitting request to proxy model=%s", model_id_with_modality)
        self._log_request(post_url, headers, payload)

        async with httpx.AsyncClient() as client:
            try:
                post_resp = await client.post(post_url, json=payload, headers=headers, timeout=60)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                self._set_safe_defaults()
                msg = f"{self.name} failed to submit request: {e}"
                raise RuntimeError(msg) from e

            if post_resp.status_code >= HTTP_CLIENT_ERROR_STATUS:
                self._set_safe_defaults()
                logger.error(
                    "Proxy POST error status=%d headers=%s body=%s",
                    post_resp.status_code,
                    dict(post_resp.headers),
                    post_resp.text,
                )
                try:
                    error_json = post_resp.json()
                    error_details = self._extract_error_from_initial_response(error_json)
                    msg = f"{self.name} request failed: {error_details}"
                except (ValueError, _json.JSONDecodeError):
                    msg = f"{self.name} request failed: HTTP {post_resp.status_code} - {post_resp.text}"
                raise RuntimeError(msg)

            try:
                post_json = post_resp.json()
            except (ValueError, _json.JSONDecodeError) as e:
                self._set_safe_defaults()
                msg = f"{self.name} received invalid JSON response: {e}"
                raise RuntimeError(msg) from e

            generation_id = str(post_json.get("generation_id") or "")

            if generation_id:
                logger.info("Submitted. generation_id=%s", generation_id)
                self.parameter_output_values["generation_id"] = generation_id
            else:
                logger.error("No generation_id returned from POST response")

            return generation_id

    def _build_payload(self, params: dict[str, Any], video_uri: str) -> dict[str, Any]:
        """Build the request payload for LTX Retake API."""
        # Convert [start, end] to start_time and duration
        segment = params["retake_segment"]
        start_time = float(segment[0])
        end_time = float(segment[1])
        duration = end_time - start_time

        payload: dict[str, Any] = {
            "video_uri": video_uri,
            "start_time": start_time,
            "duration": duration,
            "prompt": params["prompt"].strip(),
            "mode": params["mode"],
            "model": "ltx-2-pro",  # API only supports ltx-2-pro
        }

        return payload

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            logger.debug("POST %s\nheaders=%s\nbody=%s", url, dbg_headers, _json.dumps(payload, indent=2))

    async def _poll_for_result_async(self, generation_id: str, headers: dict[str, str]) -> None:
        status_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 1200.0

        async with httpx.AsyncClient() as client:
            while True:
                if monotonic() - start_time > timeout_s:
                    self._handle_polling_timeout()
                    return

                try:
                    status_resp = await client.get(status_url, headers=headers, timeout=60)
                    status_resp.raise_for_status()
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    self._handle_polling_error(exc)
                    return

                try:
                    status_json = status_resp.json()
                except (ValueError, _json.JSONDecodeError) as exc:
                    error_msg = f"Invalid JSON response during polling: {exc}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    self._handle_failure_exception(RuntimeError(error_msg))
                    return

                self.parameter_output_values["provider_response"] = status_json

                with suppress(Exception):
                    logger.debug("GET status attempt #%d: %s", attempt + 1, _json.dumps(status_json, indent=2))

                attempt += 1

                # Check status field for generation state
                status = status_json.get("status", "").upper()
                logger.info("%s polling attempt #%d status=%s", self.name, attempt, status)

                # Handle terminal states
                if status == "COMPLETED":
                    await self._fetch_and_handle_result(client, generation_id, headers)
                    return

                if status in ("FAILED", "ERRORED"):
                    self._handle_generation_failure(status_json, status)
                    return

                # Continue polling for in-progress states (QUEUED, RUNNING)
                if status in ("QUEUED", "RUNNING"):
                    await asyncio.sleep(poll_interval_s)
                    continue

                # Unknown status - log and continue polling
                logger.warning("%s unknown status '%s', continuing to poll", self.name, status)
                await asyncio.sleep(poll_interval_s)

    def _handle_polling_timeout(self) -> None:
        self.parameter_output_values["video_url"] = None
        logger.error("%s polling timed out waiting for result", self.name)
        self._set_status_results(
            was_successful=False,
            result_details="Video retake timed out after 1200 seconds waiting for result.",
        )

    def _handle_polling_error(self, exc: Exception) -> None:
        logger.error("%s GET generation status failed: %s", self.name, exc)
        error_msg = f"Failed to poll generation status: {exc}"
        self._set_status_results(was_successful=False, result_details=error_msg)
        self._handle_failure_exception(RuntimeError(error_msg))

    async def _fetch_and_handle_result(
        self, client: httpx.AsyncClient, generation_id: str, headers: dict[str, str]
    ) -> None:
        logger.info("%s generation completed, fetching result", self.name)
        result_url = urljoin(self._proxy_base, f"generations/{generation_id}/result")

        try:
            result_resp = await client.get(result_url, headers=headers, timeout=120)
            result_resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.error("%s failed to fetch result: %s", self.name, exc)
            error_msg = f"Generation completed but failed to fetch result: {exc}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(RuntimeError(error_msg))
            return

        # The /result endpoint returns raw binary MP4 data (application/octet-stream)
        video_bytes = result_resp.content
        logger.info("%s received video data: %d bytes", self.name, len(video_bytes))
        await self._handle_completion_async(video_bytes, generation_id)

    def _handle_generation_failure(self, status_json: dict[str, Any], status: str) -> None:
        # Extract error details from status_detail
        status_detail = status_json.get("status_detail", {})
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")

            # If details is a JSON string, try to parse it and extract clean error message
            if details and isinstance(details, str):
                try:
                    details_obj = _json.loads(details)
                    if isinstance(details_obj, dict):
                        # Try to extract .error.message from parsed JSON
                        error_obj = details_obj.get("error")
                        if isinstance(error_obj, dict):
                            clean_message = error_obj.get("message")
                            if clean_message:
                                details = clean_message

                except (ValueError, _json.JSONDecodeError):
                    pass

            if error and details:
                message = f"{error}: {details}"
            elif error:
                message = error
            elif details:
                message = details
            else:
                message = f"Generation {status.lower()} with no details provided"
        else:
            message = f"Generation {status.lower()} with no details provided"

        logger.error("%s generation %s: %s", self.name, status.lower(), message)
        self.parameter_output_values["video_url"] = None
        self._set_status_results(
            was_successful=False, result_details=f"{self.name} generation {status.lower()}: {message}"
        )

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

    def _extract_error_from_initial_response(self, response_json: dict[str, Any]) -> str:
        """Extract error details from initial POST response.

        Expected error shape from API:
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Prompt exceeds 5000 characters limit"
            }
        }
        """
        if not response_json:
            return "No error details provided by API."

        # Try to extract .error.message
        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                # Try to get the message field
                message = error.get("message")
                if message:
                    return str(message)

                # If no message but there's a type, include it
                error_type = error.get("type")
                if error_type:
                    return f"API error: {error_type}"

            # If error is just a string
            if isinstance(error, str):
                return error

        # Fallback: return full JSON response
        return f"Request failed: {_json.dumps(response_json)}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
