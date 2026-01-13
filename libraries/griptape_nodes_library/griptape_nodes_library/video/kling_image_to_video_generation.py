from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic
from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingImageToVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
HTTP_CLIENT_ERROR_STATUS = 400
DEFAULT_DURATION_5S = 5


class KlingImageToVideoGeneration(SuccessFailureNode):
    """Generate a video from an image using Kling AI models via Griptape Cloud model proxy.

    Inputs:
        - image (ImageArtifact|ImageUrlArtifact|str): Start frame image (required)
        - image_tail (ImageArtifact|ImageUrlArtifact|str): End frame image (optional, v2.1+ pro mode only)
        - prompt (str): Text prompt for video generation (max 2500 chars)
        - model_name (str): Model to use (default: kling-v2-1)
        - negative_prompt (str): Negative text prompt (max 2500 chars)
        - cfg_scale (float): Flexibility in video generation (0-1)
        - mode (str): Video generation mode (std: Standard, pro: Professional)
        - duration (int): Video length in seconds
        - sound (str): Generate native audio with the video (kling-v2-6 only)
        - static_mask (ImageArtifact|ImageUrlArtifact|str): Static mask for brush application
        - dynamic_masks (str): JSON string for dynamic brush configuration
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - video_id (str): The Kling AI video ID
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "kling-v1": {
            "modes": ["std", "pro"],
            "durations": [5],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v1-5": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-1": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": True,  # Only with pro mode
        },
        "kling-v2-1-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-5-turbo": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": True,  # Only with pro mode
        },
        "kling-v2-6": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": True,
            "supports_tail_frame": False,
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
                name="model_name",
                default_value="kling-v2-1",
                tooltip="Model Name for generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "kling-v1",
                            "kling-v1-5",
                            "kling-v2-master",
                            "kling-v2-1",
                            "kling-v2-1-master",
                            "kling-v2-5-turbo",
                            "kling-v2-6",
                        ]
                    )
                },
                ui_options={"display_name": "Model"},
            )
        )

        # Image Inputs Group
        with ParameterGroup(name="Image Inputs") as image_group:
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="Start frame image (required). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Start Frame"},
            )
            Parameter(
                name="image_tail",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="End frame image (optional). Supported on kling-v2-1 and kling-v2-5-turbo with pro mode.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "End Frame"},
            )
        self.add_node_element(image_group)

        # Prompts Group
        with ParameterGroup(name="Prompts") as prompts_group:
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Positive text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe the desired video content..."},
            )
            ParameterString(
                name="negative_prompt",
                default_value="",
                tooltip="Negative text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        self.add_node_element(prompts_group)

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterFloat(
                name="cfg_scale",
                default_value=0.5,
                tooltip="Flexibility (0-1). Higher value = lower flexibility, stronger prompt relevance.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode (std: Standard, pro: Professional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video length in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
            ParameterString(
                name="sound",
                default_value="off",
                tooltip="Generate native audio with the video (kling-v2-6 only)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["on", "off"])},
                ui_options={"hide": True},
            )
        self.add_node_element(gen_settings_group)

        # Masks Group
        with ParameterGroup(name="Masks") as masks_group:
            Parameter(
                name="static_mask",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Static brush application area. Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="dynamic_masks",
                default_value="",
                tooltip="JSON string for dynamic brush configuration list. Masks within JSON must be URL/Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Enter JSON for dynamic masks..."},
            )
        masks_group.ui_options = {"hide": True}
        self.add_node_element(masks_group)

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
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
                hide=True,
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

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The Kling AI video ID",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        self._update_parameter_visibility_for_model("kling-v2-1")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model_name":
            self._update_parameter_visibility_for_model(value)

    def _update_parameter_visibility_for_model(self, model_name: str) -> None:
        """Update parameter visibility based on selected model."""
        # Show mask features for all models
        self.show_parameter_by_name(["static_mask", "dynamic_masks"])

        # Show/hide image_tail (end frame) based on model support
        capabilities = self.MODEL_CAPABILITIES.get(model_name, {})
        if capabilities.get("supports_tail_frame", False):
            self.show_parameter_by_name("image_tail")
        else:
            self.hide_parameter_by_name("image_tail")

        if model_name == "kling-v1":
            self.show_parameter_by_name("mode")
            self.hide_parameter_by_name(["duration", "sound"])
            current_duration = self.get_parameter_value("duration")
            if current_duration != DEFAULT_DURATION_5S:
                self.set_parameter_value("duration", DEFAULT_DURATION_5S)
        elif model_name in {"kling-v1-5", "kling-v2-5-turbo"}:
            self.hide_parameter_by_name(["mode", "sound"])
            self.show_parameter_by_name("duration")
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
        elif model_name == "kling-v2-6":
            self.hide_parameter_by_name("mode")
            self.show_parameter_by_name(["duration", "sound"])
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
            current_duration = self.get_parameter_value("duration")
            if current_duration not in [5, 10]:
                self.set_parameter_value("duration", 5)
        else:
            self.show_parameter_by_name(["mode", "duration"])
            self.hide_parameter_by_name("sound")

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:  # noqa: PLR0911, PLR0912, PLR0915, C901
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
        params = await self._get_parameters_async()
        logger.debug(
            "%s parameters: model=%s, mode=%s, duration=%s",
            self.name,
            params["model_name"],
            params["mode"],
            params["duration"],
        )

        # Validate at least one image is provided
        if not params["image"] and not params["image_tail"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires at least one of 'image' (start frame) or 'image_tail' (end frame)."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no images provided", self.name)
            return

        # Validate prompt length
        if params["prompt"] and len(params["prompt"]) > MAX_PROMPT_LENGTH:
            self._set_safe_defaults()
            error_msg = f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (limit: {MAX_PROMPT_LENGTH})."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: prompt too long", self.name)
            return

        # Validate negative prompt length
        if params["negative_prompt"] and len(params["negative_prompt"]) > MAX_PROMPT_LENGTH:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name} negative_prompt exceeds {MAX_PROMPT_LENGTH} characters (limit: {MAX_PROMPT_LENGTH})."
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: negative prompt too long", self.name)
            return

        # Validate cfg_scale
        if not (0 <= params["cfg_scale"] <= 1):
            self._set_safe_defaults()
            error_msg = f"{self.name} cfg_scale must be between 0.0 and 1.0."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid cfg_scale", self.name)
            return

        # Validate model-specific constraints
        capabilities = self.MODEL_CAPABILITIES.get(params["model_name"], {})

        if params["mode"] not in capabilities.get("modes", ["std", "pro"]):
            self._set_safe_defaults()
            valid_modes = capabilities.get("modes", [])
            error_msg = (
                f"{self.name}: Model {params['model_name']} does not support mode '{params['mode']}'. "
                f"Valid modes: {', '.join(valid_modes)}"
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid mode for model", self.name)
            return

        if params["duration"] not in capabilities.get("durations", [5, 10]):
            self._set_safe_defaults()
            valid_durations = capabilities.get("durations", [])
            error_msg = (
                f"{self.name}: Model {params['model_name']} does not support duration {params['duration']}s. "
                f"Valid durations: {', '.join(map(str, valid_durations))}"
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid duration for model", self.name)
            return

        # Validate tail frame support
        if params["image_tail"]:
            supports_tail = capabilities.get("supports_tail_frame", False)
            if not supports_tail:
                self._set_safe_defaults()
                error_msg = (
                    f"{self.name}: Model {params['model_name']} does not support end frame (image_tail). "
                    f"Only kling-v2-1 and kling-v2-5-turbo with pro mode support end frames."
                )
                self._set_status_results(was_successful=False, result_details=error_msg)
                logger.error("%s validation failed: model doesn't support tail frame", self.name)
                return

            if supports_tail and params["mode"] != "pro":
                self._set_safe_defaults()
                error_msg = f"{self.name}: End frame (image_tail) requires pro mode."
                self._set_status_results(was_successful=False, result_details=error_msg)
                logger.error("%s validation failed: tail frame requires pro mode", self.name)
                return

        # Validate dynamic_masks JSON if provided
        if params["dynamic_masks"]:
            try:
                _json.loads(params["dynamic_masks"])
            except _json.JSONDecodeError as e:
                self._set_safe_defaults()
                error_msg = f"{self.name} dynamic_masks is not valid JSON: {e}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                logger.error("%s validation failed: invalid dynamic_masks JSON", self.name)
                return

        # Build payload
        payload = await self._build_payload_async(params)

        # Submit request
        try:
            generation_id = await self._submit_request_async(params["model_name"], payload, headers)
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

    async def _get_parameters_async(self) -> dict[str, Any]:
        """Get and process all parameters, including image conversion."""
        return {
            "model_name": self.get_parameter_value("model_name") or "kling-v2-1",
            "image": await self._prepare_image_data_url_async(self.get_parameter_value("image")),
            "image_tail": await self._prepare_image_data_url_async(self.get_parameter_value("image_tail")),
            "prompt": self.get_parameter_value("prompt") or "",
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "cfg_scale": self.get_parameter_value("cfg_scale") or 0.5,
            "mode": self.get_parameter_value("mode") or "pro",
            "duration": self.get_parameter_value("duration") or 5,
            "sound": self.get_parameter_value("sound") or "off",
            "static_mask": await self._prepare_image_data_url_async(self.get_parameter_value("static_mask")),
            "dynamic_masks": self.get_parameter_value("dynamic_masks") or "",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request_async(self, model_name: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        # Append :image2video modality to the model_id for the endpoint
        model_id_with_modality = f"{model_name}:image2video"
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

    async def _build_payload_async(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for Kling API."""
        payload: dict[str, Any] = {
            "model_name": params["model_name"],
            "duration": int(params["duration"]),
            "cfg_scale": float(params["cfg_scale"]),
            "mode": params["mode"],
        }

        # Add images
        if params["image"]:
            payload["image"] = params["image"]

        if params["image_tail"]:
            payload["image_tail"] = params["image_tail"]

        # Add prompts if provided
        if params["prompt"]:
            payload["prompt"] = params["prompt"].strip()

        if params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"].strip()

        # Add sound parameter for v2.6
        if params["model_name"] == "kling-v2-6" and params["sound"]:
            payload["sound"] = params["sound"]

        # Add masks if provided
        if params["static_mask"]:
            payload["static_mask"] = params["static_mask"]

        if params["dynamic_masks"]:
            with suppress(_json.JSONDecodeError):
                payload["dynamic_masks"] = _json.loads(params["dynamic_masks"])

        return payload

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        """Convert image input to a data URL, handling external URLs by downloading and converting."""
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # If it's already a data URL, return it
        if image_url.startswith("data:image/"):
            return image_url

        # If it's an external URL, download and convert to data URL
        if image_url.startswith(("http://", "https://")):
            return await self._inline_external_url_async(image_url)

        return image_url

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Download external image URL and convert to data URL."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.debug("%s failed to inline image URL: %s", self.name, e)
                return None
            else:
                content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("Image URL converted to data URI for proxy")
                return b64

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:
            try:
                from copy import deepcopy

                red = deepcopy(b)
                # Redact data URLs in images and masks
                for key in ("image", "image_tail", "static_mask"):
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
        """Handle successful completion by downloading and saving the video.

        The result JSON shape is the same as the Kling API used by the old node.
        Expected structure: {"data": {"task_result": {"videos": [{"url": "...", "id": "..."}]}}}
        """
        data = response_json.get("data", {})
        task_result = data.get("task_result", {})
        videos = task_result.get("videos", [])

        if not videos or not isinstance(videos, list) or len(videos) == 0:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no videos found in response.",
            )
            return

        video_info = videos[0]
        download_url = video_info.get("url")
        video_id = video_info.get("id")

        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download URL found in response.",
            )
            return

        # Set kling_video_id output parameter
        if video_id:
            self.parameter_output_values["kling_video_id"] = video_id
            logger.info("Video ID: %s", video_id)

        try:
            logger.info("%s downloading video from provider URL", self.name)
            video_bytes = await self._download_bytes_from_url_async(download_url)
        except (httpx.HTTPError, httpx.TimeoutException, RuntimeError) as e:
            logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"kling_image_to_video_{generation_id}.mp4"
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

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["kling_video_id"] = ""

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
