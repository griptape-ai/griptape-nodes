from __future__ import annotations

import asyncio
import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic
from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXTextToVideoGeneration"]

# Constants
HTTP_CLIENT_ERROR_STATUS = 400

# Model mapping from display names to API model IDs
MODEL_MAPPING = {
    "LTX 2 Pro": "ltx-2-pro",
    "LTX 2 Fast": "ltx-2-fast",
}

# Camera motion options
CAMERA_MOTION_OPTIONS = [
    "static",
    "dolly_in",
    "dolly_out",
    "dolly_left",
    "dolly_right",
    "jib_up",
    "jib_down",
]


class LTXTextToVideoGeneration(SuccessFailureNode):
    """Generate a video from text using LTX AI models via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for video generation (required)
        - model (str): Model to use (LTX 2 Pro or LTX 2 Fast)
        - resolution (str): Video resolution (1920x1080, 2560x1440, or 3840x2160)
        - duration (int): Video length in seconds
        - fps (int): Frames per second (default: 25)
        - camera_motion (str): Camera movement type (default: static)
        - generate_audio (bool): Generate audio with the video (default: true)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "ltx-2-fast": {
            "resolutions": {
                "1920x1080": {
                    "fps": {25: [6, 8, 10, 12, 14, 16, 18, 20], 50: [6, 8, 10]},
                },
                "2560x1440": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "3840x2160": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
            }
        },
        "ltx-2-pro": {
            "resolutions": {
                "1920x1080": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "2560x1440": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "3840x2160": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
            }
        },
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="LTX 2 Fast",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["LTX 2 Pro", "LTX 2 Fast"])},
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video you want to generate...",
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="resolution",
                default_value="1920x1080",
                tooltip="Video resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["1920x1080", "2560x1440", "3840x2160"])},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="duration",
                default_value=6,
                tooltip="Video length in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[6, 8, 10, 12, 14, 16, 18, 20])},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="fps",
                default_value=25,
                tooltip="Frames per second",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[25, 50])},
            )
        )

        self.add_parameter(
            ParameterString(
                name="camera_motion",
                default_value="static",
                tooltip="Camera movement type",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=CAMERA_MOTION_OPTIONS)},
            )
        )

        self.add_parameter(
            ParameterBool(
                name="generate_audio",
                default_value=True,
                tooltip="Generate audio with the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

        # Set initial parameter visibility based on default model
        self._update_parameter_visibility_for_model("LTX 2 Fast")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model":
            self._update_parameter_visibility_for_model(value)

    def _update_parameter_visibility_for_model(self, model_name: str) -> None:
        """Update parameter visibility and options based on selected model."""
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-fast")
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})

        # Get available resolutions
        available_resolutions = list(capabilities.get("resolutions", {}).keys())

        # Update resolution options
        resolution_param = self.get_parameter_by_name("resolution")
        if resolution_param and available_resolutions:
            current_resolution = self.get_parameter_value("resolution")
            if current_resolution not in available_resolutions:
                self.set_parameter_value("resolution", available_resolutions[0])

        # Update duration options based on model
        if model_id == "ltx-2-fast":
            duration_param = self.get_parameter_by_name("duration")
            if duration_param:
                # ltx-2-fast can support up to 20s at 1920x1080@25fps
                current_resolution = self.get_parameter_value("resolution") or "1920x1080"
                current_fps = self.get_parameter_value("fps") or 25
                resolution_config = capabilities.get("resolutions", {}).get(current_resolution, {})
                fps_config = resolution_config.get("fps", {})
                available_durations = fps_config.get(current_fps, [6, 8, 10])

                # Update duration trait options
                duration_trait = duration_param.find_elements_by_type(Options)
                if duration_trait:
                    duration_trait[0].choices = available_durations

                # Validate current duration
                current_duration = self.get_parameter_value("duration")
                if current_duration not in available_durations:
                    self.set_parameter_value("duration", available_durations[0])

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()
        logger.info("%s starting video generation", self.name)

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
            "%s parameters: model=%s, prompt_length=%d, resolution=%s, duration=%s, fps=%s",
            self.name,
            params["model"],
            len(params["prompt"]),
            params["resolution"],
            params["duration"],
            params["fps"],
        )

        # Validate prompt is provided
        if not params["prompt"].strip():
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a prompt to generate video."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: empty prompt", self.name)
            return

        # Validate model-resolution-fps-duration combination
        validation_error = self._validate_model_params(params)
        if validation_error:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=validation_error)
            logger.error("%s validation failed: %s", self.name, validation_error)
            return

        # Build payload
        payload = self._build_payload(params)

        # Submit request
        try:
            generation_id = await self._submit_request_async(params["model"], payload, headers)
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
            "model": self.get_parameter_value("model") or "LTX 2 Fast",
            "resolution": self.get_parameter_value("resolution") or "1920x1080",
            "duration": self.get_parameter_value("duration") or 6,
            "fps": self.get_parameter_value("fps") or 25,
            "camera_motion": self.get_parameter_value("camera_motion") or "static",
            "generate_audio": self.get_parameter_value("generate_audio")
            if self.get_parameter_value("generate_audio") is not None
            else True,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _validate_model_params(self, params: dict[str, Any]) -> str | None:
        """Validate that the model-resolution-fps-duration combination is supported."""
        model_display_name = params["model"]
        model_id = MODEL_MAPPING.get(model_display_name, "ltx-2-fast")
        resolution = params["resolution"]
        fps = params["fps"]
        duration = params["duration"]

        capabilities = self.MODEL_CAPABILITIES.get(model_id)
        if not capabilities:
            return f"{self.name}: Unknown model '{model_display_name}'"

        resolution_config = capabilities.get("resolutions", {}).get(resolution)
        if not resolution_config:
            valid_resolutions = list(capabilities.get("resolutions", {}).keys())
            return (
                f"{self.name}: Model {model_display_name} does not support resolution '{resolution}'. "
                f"Valid resolutions: {', '.join(valid_resolutions)}"
            )

        fps_config = resolution_config.get("fps", {})
        supported_durations = fps_config.get(fps)
        if supported_durations is None:
            valid_fps = list(fps_config.keys())
            return (
                f"{self.name}: Model {model_display_name} does not support {fps} FPS at resolution {resolution}. "
                f"Valid FPS values: {', '.join(map(str, valid_fps))}"
            )

        if duration not in supported_durations:
            return (
                f"{self.name}: Model {model_display_name} does not support duration {duration}s "
                f"at resolution {resolution} and {fps} FPS. "
                f"Valid durations: {', '.join(map(str, supported_durations))}"
            )

        return None

    async def _submit_request_async(self, model_name: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        # Map display name to model ID and append :text-to-video modality
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-fast")
        model_id_with_modality = f"{model_id}:text-to-video"
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

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for LTX API."""
        # Map display name to model ID (without modality)
        model_id = MODEL_MAPPING.get(params["model"], "ltx-2-fast")

        payload: dict[str, Any] = {
            "prompt": params["prompt"].strip(),
            "model": model_id,
            "duration": int(params["duration"]),
            "resolution": params["resolution"],
            "fps": int(params["fps"]),
            "camera_motion": params["camera_motion"],
            "generate_audio": bool(params["generate_audio"]),
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
            result_details="Video generation timed out after 1200 seconds waiting for result.",
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
            filename = f"ltx_text_to_video_{generation_id}.mp4"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            logger.info("%s saved video to static storage as %s", self.name, filename)
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
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
