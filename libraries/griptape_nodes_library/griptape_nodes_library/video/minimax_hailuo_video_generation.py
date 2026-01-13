from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import os
from contextlib import suppress
from copy import deepcopy
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

__all__ = ["MinimaxHailuoVideoGeneration"]


class MinimaxHailuoVideoGeneration(SuccessFailureNode):
    """Generate a video using the MiniMax Hailuo model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Model to use (default: Hailuo 2.3)
        - duration (int): Video duration in seconds (default: 6, options depend on model)
        - resolution (str): Output resolution (options depend on model and duration)
        - prompt_optimizer (bool): Enable prompt optimization (default: False)
        - fast_pretreatment (bool): Reduce optimization time for Hailuo 2.3/02 models (default: False)
        - first_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (data URL)
        - last_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for Hailuo 02 model (data URL)
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

    # Model capability definitions (keyed by provider model IDs)
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "MiniMax-Hailuo-2.3": {
            "durations": [6, 10],
            "resolutions": {"6": ["768p", "1080p"], "10": ["768p"]},
            "default_resolution": {"6": "768p", "10": "768p"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-02": {
            "durations": [6, 10],
            "resolutions": {"6": ["768p", "1080p"], "10": ["768p"]},
            "default_resolution": {"6": "768p", "10": "768p"},
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-2.3-Fast": {
            "durations": [6],
            "resolutions": {"6": ["720p", "1080p"]},
            "default_resolution": {"6": "720p"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": False,
        },
    }

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Hailuo 2.3 (TTV & ITV)": "MiniMax-Hailuo-2.3",
        "Hailuo 02 (TTV & ITV)": "MiniMax-Hailuo-02",
        "Hailuo 2.3 Fast (ITV)": "MiniMax-Hailuo-2.3-Fast",
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
                name="model_id",
                default_value="Hailuo 2.3 (TTV & ITV)",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "Hailuo 2.3 (TTV & ITV)",
                            "Hailuo 02 (TTV & ITV)",
                            "Hailuo 2.3 Fast (ITV)",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "prompt",
                },
            )
        )

        # Duration in seconds
        self.add_parameter(
            ParameterInt(
                name="duration",
                default_value=6,
                tooltip="Video duration in seconds (options depend on model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[6, 10])},
            )
        )

        # Resolution selection
        self.add_parameter(
            ParameterString(
                name="resolution",
                default_value="768p",
                tooltip="Output resolution (options depend on model and duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "768p", "1080p"])},
            )
        )

        # Prompt optimizer flag
        self.add_parameter(
            ParameterBool(
                name="prompt_optimizer",
                default_value=False,
                tooltip="Enable prompt optimization",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Fast pretreatment flag (only for 2.3 and 02 models)
        self.add_parameter(
            ParameterBool(
                name="fast_pretreatment",
                default_value=False,
                tooltip="Reduce optimization time (only for Hailuo 2.3 and Hailuo 02)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide": False},
            )
        )

        # Optional first frame (image) - accepts artifact or data URL string
        self.add_parameter(
            Parameter(
                name="first_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip=(
                    "Optional first frame image as data URL (data:image/jpeg;base64,...). "
                    "Supported formats: JPG, JPEG, PNG, WebP. Requirements: <20MB, short edge >300px, "
                    "aspect ratio between 2:5 and 5:2."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "First Frame Image"},
            )
        )

        # Optional last frame (image) - only for 02 model
        self.add_parameter(
            Parameter(
                name="last_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip=(
                    "Optional last frame image for Hailuo 02 model as data URL (data:image/jpeg;base64,...). "
                    "Supported formats: JPG, JPEG, PNG, WebP. Requirements: <20MB, short edge >300px, "
                    "aspect ratio between 2:5 and 5:2."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame Image", "hide": True},
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
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        default_model = "Hailuo 2.3 (TTV & ITV)"
        default_provider_model_id = self._get_provider_model_id(default_model)
        default_capabilities = self.MODEL_CAPABILITIES.get(default_provider_model_id, {})

        # Show/hide last_frame_image based on default model
        if default_capabilities.get("supports_last_frame", False):
            self.show_parameter_by_name("last_frame_image")
        else:
            self.hide_parameter_by_name("last_frame_image")

        # Show/hide fast_pretreatment based on default model
        if default_capabilities.get("supports_fast_pretreatment", False):
            self.show_parameter_by_name("fast_pretreatment")
        else:
            self.hide_parameter_by_name("fast_pretreatment")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model_id":
            # Convert friendly name to provider model ID
            provider_model_id = self._get_provider_model_id(value)

            # Show/hide last_frame_image parameter only for 02 model
            capabilities = self.MODEL_CAPABILITIES.get(provider_model_id, {})
            show_last_frame = capabilities.get("supports_last_frame", False)
            if show_last_frame:
                self.show_parameter_by_name("last_frame_image")
            else:
                self.hide_parameter_by_name("last_frame_image")

            # Show/hide fast_pretreatment based on model support
            show_fast_pretreatment = capabilities.get("supports_fast_pretreatment", False)
            if show_fast_pretreatment:
                self.show_parameter_by_name("fast_pretreatment")
            else:
                self.hide_parameter_by_name("fast_pretreatment")

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
            "%s parameters: model=%s, prompt_length=%d, duration=%s, resolution=%s",
            self.name,
            params["model_id"],
            len(params["prompt"]),
            params["duration"],
            params["resolution"],
        )

        # Validate prompt is provided
        if not params["prompt"].strip():
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a prompt to generate video."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: empty prompt", self.name)
            return

        # Validate model-specific requirements
        if params["model_id"] == "MiniMax-Hailuo-2.3-Fast" and not params["first_frame_image"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a first frame image for Hailuo 2.3 Fast model (image-to-video only)."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: Hailuo 2.3 Fast requires first frame image", self.name)
            return

        # Validate duration/resolution combination
        capabilities = self.MODEL_CAPABILITIES.get(params["model_id"], {})
        valid_resolutions = capabilities.get("resolutions", {}).get(str(params["duration"]), [])
        if valid_resolutions and params["resolution"] not in valid_resolutions:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name}: Model {params['model_id']} does not support the combination of "
                f"duration {params['duration']}s and resolution {params['resolution']}. "
                f"Valid resolutions for {params['duration']}s: {', '.join(valid_resolutions)}"
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid duration/resolution combination", self.name)
            return

        # Build payload
        payload = await self._build_payload_async(params)

        # Submit request
        try:
            generation_id = await self._submit_request_async(params["model_id"], payload, headers)
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
        raw_model_id = self.get_parameter_value("model_id") or "Hailuo 2.3 (TTV & ITV)"
        # Convert friendly name to provider model ID
        model_id = self._get_provider_model_id(raw_model_id)

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": model_id,
            "duration": self.get_parameter_value("duration"),
            "resolution": self.get_parameter_value("resolution") or "768p",
            "prompt_optimizer": self.get_parameter_value("prompt_optimizer"),
            "fast_pretreatment": self.get_parameter_value("fast_pretreatment"),
            "first_frame_image": self.get_parameter_value("first_frame_image"),
            "last_frame_image": self.get_parameter_value("last_frame_image"),
        }

    @classmethod
    def _get_provider_model_id(cls, user_facing_name: str) -> str:
        """Convert user-facing model name to provider model ID.

        Falls back to the input value if it's not in the mapping (for backwards compatibility
        with saved flows that may have old model IDs).
        """
        return cls.MODEL_NAME_MAP.get(user_facing_name, user_facing_name)

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request_async(self, model_id: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{model_id}")

        logger.info("Submitting request to proxy model=%s", model_id)
        self._log_request(post_url, headers, payload)

        async with httpx.AsyncClient() as client:
            try:
                post_resp = await client.post(post_url, json=payload, headers=headers, timeout=60)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                self._set_safe_defaults()
                msg = f"{self.name} failed to submit request: {e}"
                raise RuntimeError(msg) from e

            if post_resp.status_code >= 400:  # noqa: PLR2004
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

    async def _build_payload_async(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for MiniMax Hailuo API."""
        model_id = params["model_id"]
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": params["prompt"].strip(),
        }

        # Add duration
        if params["duration"] is not None:
            payload["duration"] = int(params["duration"])

        # Add resolution (uppercase for API)
        if params["resolution"]:
            payload["resolution"] = params["resolution"].upper()

        # Always send prompt_optimizer (defaults to False)
        payload["prompt_optimizer"] = bool(params["prompt_optimizer"])

        # Add fast_pretreatment only for models that support it
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})
        if capabilities.get("supports_fast_pretreatment", False):
            payload["fast_pretreatment"] = bool(params["fast_pretreatment"])

        # Add first_frame_image if provided and model supports it
        if capabilities.get("supports_first_frame", False):
            first_frame_data_url = await self._prepare_frame_data_url_async(params["first_frame_image"])
            if first_frame_data_url:
                payload["first_frame_image"] = first_frame_data_url

        # Add last_frame_image if provided and model supports it
        if capabilities.get("supports_last_frame", False):
            last_frame_data_url = await self._prepare_frame_data_url_async(params["last_frame_image"])
            if last_frame_data_url:
                payload["last_frame_image"] = last_frame_data_url

        return payload

    async def _prepare_frame_data_url_async(self, frame_input: Any) -> str | None:
        """Convert frame input to a data URL, handling external URLs by downloading and converting."""
        if not frame_input:
            return None

        frame_url = self._coerce_image_url_or_data_uri(frame_input)
        if not frame_url:
            return None

        # If it's already a data URL, return it
        if frame_url.startswith("data:image/"):
            return frame_url

        # If it's an external URL, download and convert to data URL
        if frame_url.startswith(("http://", "https://")):
            return await self._inline_external_url_async(frame_url)

        return frame_url

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Download external image URL and convert to data URL."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.debug("%s failed to inline frame URL: %s", self.name, e)
                return None
            else:
                content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("Frame URL converted to data URI for proxy")
                return f"data:{content_type};base64,{b64}"

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:
            try:
                red = deepcopy(b)
                # Redact data URLs in frame images
                for key in ("first_frame_image", "last_frame_image"):
                    if key in red and isinstance(red[key], str) and red[key].startswith("data:image/"):
                        parts = red[key].split(",", 1)
                        header = parts[0] if parts else "data:image/"
                        b64 = parts[1] if len(parts) > 1 else ""
                        red[key] = f"{header},<redacted base64 length={len(b64)}>"
            except (KeyError, TypeError, ValueError):
                return b
            else:
                return red

        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            logger.debug(
                "POST %s\nheaders=%s\nbody=%s", url, dbg_headers, _json.dumps(_sanitize_body(payload), indent=2)
            )

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
            result_resp = await client.get(result_url, headers=headers, timeout=60)
            result_resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.error("%s failed to fetch result: %s", self.name, exc)
            error_msg = f"Generation completed but failed to fetch result: {exc}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(RuntimeError(error_msg))
            return

        try:
            result_json = result_resp.json()
        except (ValueError, _json.JSONDecodeError) as exc:
            logger.error("%s received invalid JSON in result: %s", self.name, exc)
            error_msg = f"Generation completed but received invalid JSON: {exc}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(RuntimeError(error_msg))
            return

        self.parameter_output_values["provider_response"] = result_json
        with suppress(Exception):
            logger.debug("GET result: %s", _json.dumps(result_json, indent=2))
        await self._handle_completion_async(result_json, generation_id)

    def _handle_generation_failure(self, status_json: dict[str, Any], status: str) -> None:
        # Extract error details from status_detail
        status_detail = status_json.get("status_detail", {})
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")
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

    async def _handle_completion_async(self, response_json: dict[str, Any], generation_id: str) -> None:
        """Handle successful completion by downloading and saving the video."""
        file_obj = response_json.get("file")
        if not isinstance(file_obj, dict):
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no file object found in response.",
            )
            return

        download_url = file_obj.get("download_url")
        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download_url found in response.",
            )
            return

        try:
            logger.info("%s downloading video from provider URL", self.name)
            video_bytes = await self._download_bytes_from_url_async(download_url)
        except (httpx.HTTPError, httpx.TimeoutException, RuntimeError) as e:
            logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"minimax_hailuo_video_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("%s saved video to static storage as %s", self.name, filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except (OSError, PermissionError) as e:
                logger.warning("%s failed to save to static storage: %s, using provider URL", self.name, e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_from_initial_response(self, response_json: dict[str, Any]) -> str:
        """Extract error details from initial POST response."""
        if not response_json:
            return "No error details provided by API."

        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message", str(error))
                return message
            return str(error)

        return "Request failed with no error details provided."

    def _extract_error_from_poll_response(self, response_json: dict[str, Any]) -> str:
        """Extract error details from polling response using base_resp.status_msg."""
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        base_resp = response_json.get("base_resp")
        if isinstance(base_resp, dict):
            status_msg = base_resp.get("status_msg")
            if status_msg:
                return f"{self.name} generation failed: {status_msg}"

        return f"{self.name} generation failed with no error details in response."

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        """Convert various image input types to a URL or data URI string."""
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except AttributeError:
            pass

        return None

    @staticmethod
    async def _download_bytes_from_url_async(url: str) -> bytes | None:
        """Download file from URL and return bytes."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=300)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException):
                return None
            else:
                return resp.content
