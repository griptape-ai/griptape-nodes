from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from time import monotonic, sleep
from typing import Any, ClassVar
from urllib.parse import urljoin

import requests
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedanceVideoGeneration"]


class SeedanceVideoGeneration(SuccessFailureNode):
    """Generate a video using the Seedance model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (supports provider flags like --resolution)
        - model_id (str): Provider model id (default: seedance-1-0-pro-250528)
        - resolution (str): Output resolution (default: 720p, options: 480p, 720p, 1080p)
        - ratio (str): Output aspect ratio (default: 16:9, options: auto, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16)
        - duration (int): Video duration in seconds (default: 5, options: 4-12)
        - camerafixed (bool): Camera fixed flag (default: False)
        - audio (bool): Generate audio with video (default: False, only for seedance-1-5-pro-251215)
        - first_frame (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (URL or base64 data URI)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for i2v and 1.5 pro models (URL or base64 data URI)
        (Always polls for result: 5s interval, 10 min timeout)

    Model capabilities:
        - seedance-1-5-pro-251215: 480p/720p, 4-12s duration, first+last frame, audio support
        - seedance-1-0-pro-250528: 480p/720p/1080p, 5s/10s duration, first+last frame
        - seedance-1-0-pro-fast-251015: 480p/720p/1080p, 5s/10s duration, first frame only
        - seedance-1-0-lite-t2v-250428: Text-to-video only (no images)
        - seedance-1-0-lite-i2v-250428: 1-4 reference images OR first+last frame OR first frame only

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    # Base URL is derived from env var and joined with /api/ at runtime

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Seedance 1.5 Pro": "seedance-1-5-pro-251215",
        "Seedance 1.0 Pro": "seedance-1-0-pro-250528",
        "Seedance 1.0 Pro Fast": "seedance-1-0-pro-fast-251015",
        "Seedance 1.0 Lite T2V": "seedance-1-0-lite-t2v-250428",
        "Seedance 1.0 Lite I2V": "seedance-1-0-lite-i2v-250428",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Seedance through Griptape Cloud model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="Seedance 1.0 Pro",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "Seedance 1.5 Pro",
                            "Seedance 1.0 Pro",
                            "Seedance 1.0 Pro Fast",
                            "Seedance 1.0 Lite T2V",
                            "Seedance 1.0 Lite I2V",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video (supports provider flags)",
                multiline=True,
                placeholder_text="Describe the video...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )
        # Optional first frame (image) - accepts artifact or URL/base64 string
        self.add_parameter(
            Parameter(
                name="first_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional first frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "First Frame"},
            )
        )

        # Optional last frame (image) - accepts artifact or URL/base64 string valid only with seedance-1-0-lite-i2v
        self.add_parameter(
            Parameter(
                name="last_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional Last frame image for seedance-1-0-lite-i2v model(URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame"},
            )
        )

        # Optional reference images (list of images) - for seedance-1-0-lite-i2v model (1-4 images)
        self.add_parameter(
            ParameterList(
                name="reference_images",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                default_value=[],
                tooltip="Optional reference images (1-4 images) for seedance-1-0-lite-i2v model",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Reference Images", "expander": True},
                max_items=4,
            )
        )

        with ParameterGroup(name="Generation Settings") as video_generation_settings_group:
            # Resolution selection
            ParameterString(
                name="resolution",
                default_value="720p",
                tooltip="Output resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["480p", "720p", "1080p"])},
            )

            # Aspect ratio selection
            ParameterString(
                name="ratio",
                default_value="adaptive",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"])},
            )

            # Duration in seconds
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[4, 5, 6, 7, 8, 9, 10, 11, 12])},
            )

            # Camera fixed flag
            ParameterBool(
                name="camerafixed",
                default_value=False,
                tooltip="Camera fixed",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            # Audio generation flag
            ParameterBool(
                name="generate_audio",
                default_value=False,
                tooltip="Generate audio with video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(video_generation_settings_group)

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
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
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
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
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        default_model = "Seedance 1.0 Pro"
        default_provider_model_id = self._get_provider_model_id(default_model)
        if default_provider_model_id == "seedance-1-0-lite-t2v-250428":
            # T2V only - hide all image inputs
            self.hide_parameter_by_name("first_frame")
            self.hide_parameter_by_name("last_frame")
            self.hide_parameter_by_name("reference_images")
        elif default_provider_model_id == "seedance-1-0-lite-i2v-250428":
            # Lite I2V - show all image inputs (user can choose reference images OR first/last frame)
            self.show_parameter_by_name("first_frame")
            self.show_parameter_by_name("last_frame")
            self.show_parameter_by_name("reference_images")
        else:
            # Other models - show first_frame, conditionally show last_frame, hide reference_images
            self.show_parameter_by_name("first_frame")
            self.hide_parameter_by_name("reference_images")
            supports_last_frame = default_provider_model_id in (
                "seedance-1-5-pro-251215",
                "seedance-1-0-pro-250528",
            )
            if supports_last_frame:
                self.show_parameter_by_name("last_frame")
            else:
                self.hide_parameter_by_name("last_frame")

        # Hide audio parameter by default (only show for 1.5 pro)
        if default_provider_model_id == "seedance-1-5-pro-251215":
            self.show_parameter_by_name("generate_audio")
        else:
            self.hide_parameter_by_name("generate_audio")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters based on model capabilities.

        Model capabilities:
        - seedance-1-5-pro-251215: text-to-video, i2v with first frame, i2v with first+last frame, audio support
        - seedance-1-0-pro-250528: i2v with first+last frame, i2v with first frame, text-to-video
        - seedance-1-0-pro-fast-251015: i2v with first frame only, text-to-video
        - seedance-1-0-lite-t2v-250428: text-to-video only (no images)
        - seedance-1-0-lite-i2v-250428: i2v with reference images, i2v with first+last frame, i2v with first frame
        """
        if parameter.name == "model_id":
            # Convert friendly name to provider model ID
            provider_model_id = self._get_provider_model_id(value)

            if provider_model_id == "seedance-1-0-lite-t2v-250428":
                # T2V only - hide all image inputs
                self.hide_parameter_by_name("first_frame")
                self.hide_parameter_by_name("last_frame")
                self.hide_parameter_by_name("reference_images")
            elif provider_model_id == "seedance-1-0-lite-i2v-250428":
                # Lite I2V - show all image inputs (user can choose reference images OR first/last frame)
                self.show_parameter_by_name("first_frame")
                self.show_parameter_by_name("last_frame")
                self.show_parameter_by_name("reference_images")
            else:
                # Other models - show first_frame, conditionally show last_frame, hide reference_images
                self.show_parameter_by_name("first_frame")
                self.hide_parameter_by_name("reference_images")
                supports_last_frame = provider_model_id in (
                    "seedance-1-5-pro-251215",
                    "seedance-1-0-pro-250528",
                )
                if supports_last_frame:
                    self.show_parameter_by_name("last_frame")
                else:
                    self.hide_parameter_by_name("last_frame")

            # Show audio parameter only for 1.5 pro model
            if provider_model_id == "seedance-1-5-pro-251215":
                self.show_parameter_by_name("generate_audio")
            else:
                self.hide_parameter_by_name("generate_audio")

        return super().after_value_set(parameter, value)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

        # No separate status message panel; we'll stream updates to the 'status' output
        # Always polls with fixed interval/timeout

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Get parameters and validate API key
        params = self._get_parameters()

        # Validate parameters
        try:
            self._validate_parameters(params)
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Build and submit request
        try:
            generation_id = self._submit_request(params, headers)
            if not generation_id:
                self.parameter_output_values["result"] = None
                self.parameter_output_values["video_url"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            # HTTP error during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        raw_model_id = self.get_parameter_value("model_id") or "Seedance 1.0 Pro"
        # Convert friendly name to provider model ID
        model_id = self._get_provider_model_id(raw_model_id)

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": model_id,
            "resolution": self.get_parameter_value("resolution") or "720p",
            "ratio": self.get_parameter_value("ratio") or "adaptive",
            "first_frame": self.get_parameter_value("first_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "reference_images": self.get_parameter_value("reference_images"),
            "duration": self.get_parameter_value("duration"),
            "camerafixed": self.get_parameter_value("camerafixed"),
            "generate_audio": self.get_parameter_value("generate_audio"),
        }

    @classmethod
    def _get_provider_model_id(cls, user_facing_name: str) -> str:
        """Convert user-facing model name to provider model ID.

        Falls back to the input value if it's not in the mapping (for backwards compatibility
        with saved flows that may have old model IDs).
        """
        return cls.MODEL_NAME_MAP.get(user_facing_name, user_facing_name)

    def _validate_parameters(self, params: dict[str, Any]) -> None:
        """Validate parameter combinations.

        Raises:
            ValueError: If invalid parameter combinations are detected
        """
        model_id = params["model_id"]

        # For lite-i2v model, check if both reference_images and first/last frames are provided
        if model_id == "seedance-1-0-lite-i2v-250428":
            has_reference_images = (
                params.get("reference_images")
                and isinstance(params.get("reference_images"), list)
                and len(params.get("reference_images", [])) > 0
            )
            has_first_or_last_frame = params.get("first_frame") is not None or params.get("last_frame") is not None

            if has_reference_images and has_first_or_last_frame:
                msg = (
                    f"{self.name}: Cannot use both reference_images and first_frame/last_frame for Seedance 1.0 Lite I2V. "
                    "Please use either reference_images (1-4 images) OR first_frame/last_frame, not both."
                )
                raise ValueError(msg)

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model_id']}")
        payload = self._build_payload(params)

        self._log(f"Submitting request to proxy model={params['model_id']}")
        self._log_request(post_url, headers, payload)

        post_resp = requests.post(post_url, json=payload, headers=headers, timeout=60)
        if post_resp.status_code >= 400:  # noqa: PLR2004
            self._set_safe_defaults()
            self._log(
                f"Proxy POST error status={post_resp.status_code} headers={dict(post_resp.headers)} body={post_resp.text}"
            )
            # Try to parse error response body
            try:
                error_json = post_resp.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"Proxy POST error: {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        post_json = post_resp.json()
        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response

        if generation_id:
            self._log(f"Submitted. generation_id={generation_id}")
        else:
            self._log("No generation_id returned from POST response")

        return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        # Build content array with text prompt
        prompt_text = params["prompt"].strip()

        # Build payload with config params at top level
        payload: dict[str, Any] = {
            "model": params["model_id"],
        }

        # Add config parameters at top level
        if params["resolution"]:
            payload["resolution"] = params["resolution"]
            prompt_text += f" --resolution {params['resolution']}"
        if params["ratio"]:
            payload["ratio"] = params["ratio"]
            prompt_text += f" --ratio {params['ratio']}"
        if params["duration"] is not None:
            payload["duration"] = int(params["duration"])
            prompt_text += f" --duration {int(params['duration'])}"
        if params["camerafixed"] is not None:
            payload["camerafixed"] = bool(params["camerafixed"])
            prompt_text += f" --camerafixed {str(bool(params['camerafixed'])).lower()}"
        # Only add audio flag for 1.5 pro model
        if params["model_id"] == "seedance-1-5-pro-251215" and params["generate_audio"] is not None:
            payload["generate_audio"] = bool(params["generate_audio"])

        content_list = [{"type": "text", "text": prompt_text}]

        # Add frame images based on model capabilities
        self._add_frame_images(content_list, params)

        payload["content"] = content_list

        return payload

    def _add_frame_images(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frame images to content list based on model capabilities.

        Different models support different image inputs:
        - seedance-1-5-pro: text-to-video, i2v with first frame, i2v with first+last frame
        - seedance-1-0-pro: i2v with first+last frame, i2v with first frame, text-to-video
        - seedance-1-0-lite-t2v: text-to-video only (no images)
        - seedance-1-0-lite-i2v: i2v with 1-4 reference images OR i2v with first+last frame OR i2v with first frame

        Role is always specified in image_url object: "first_frame", "last_frame", or "reference_image"

        For lite-i2v model, if reference_images is provided, use those instead of first/last frames.
        """
        model_id = params["model_id"]

        # seedance-1-0-lite-t2v only supports text-to-video, no images
        if model_id == "seedance-1-0-lite-t2v-250428":
            return

        # For lite-i2v model, check if reference_images is provided (takes priority)
        if model_id == "seedance-1-0-lite-i2v-250428":
            reference_images = params.get("reference_images")
            if reference_images and isinstance(reference_images, list) and len(reference_images) > 0:
                # Add up to 4 reference images
                for _i, ref_image in enumerate(reference_images[:4]):
                    ref_url = self._prepare_frame_url(ref_image)
                    if ref_url:
                        content_list.append(
                            {"type": "image_url", "image_url": {"url": ref_url}, "role": "reference_image"}
                        )
                # If reference images are provided, don't add first/last frames
                return

        # Determine which frames this model supports
        supports_last_frame = model_id in (
            "seedance-1-5-pro-251215",
            "seedance-1-0-pro-250528",
            "seedance-1-0-lite-i2v-250428",
        )

        # Add first_frame if provided
        first_frame_url = self._prepare_frame_url(params["first_frame"])
        if first_frame_url:
            content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})

        # Add last_frame only if model supports it and it's provided
        if supports_last_frame:
            last_frame_url = self._prepare_frame_url(params["last_frame"])
            if last_frame_url:
                content_list.append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})

    def _prepare_frame_url(self, frame_input: Any) -> str | None:
        """Convert frame input to a usable URL, handling inlining of external URLs."""
        if not frame_input:
            return None

        frame_url = self._coerce_image_url_or_data_uri(frame_input)
        if not frame_url:
            return None
        return self._inline_external_url(frame_url)

    def _inline_external_url(self, url: str) -> str | None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return url

        try:
            rff = requests.get(url, timeout=20)
            rff.raise_for_status()
            ct = (rff.headers.get("content-type") or "image/jpeg").split(";")[0]
            if not ct.startswith("image/"):
                ct = "image/jpeg"
            b64 = base64.b64encode(rff.content).decode("utf-8")
            self._log("Frame URL converted to data URI for proxy")
            return f"data:{ct};base64,{b64}"  # noqa: TRY300
        except Exception as e:
            self._log(f"Warning: failed to inline frame URL: {e}")
            return url

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:
            try:
                red = deepcopy(b)
                cont = red.get("content", [])
                for it in cont:
                    if isinstance(it, dict) and it.get("type") == "image_url":
                        iu = it.get("image_url") or {}
                        url_val = iu.get("url")
                        if isinstance(url_val, str) and url_val.startswith("data:image/"):
                            parts = url_val.split(",", 1)
                            header = parts[0] if parts else "data:image/"
                            b64 = parts[1] if len(parts) > 1 else ""
                            iu["url"] = f"{header},<redacted base64 length={len(b64)}>"
                return red  # noqa: TRY300
            except Exception:
                return b

        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            self._log(f"POST {url}\nheaders={dbg_headers}\nbody={_json.dumps(_sanitize_body(payload), indent=2)}")

    def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 600.0

        while True:
            if monotonic() - start_time > timeout_s:
                self.parameter_output_values["video_url"] = self._extract_video_url(last_json)
                self._log("Polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Video generation timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()
                last_json = get_resp.json()
                # Update provider_response with latest polling data
                self.parameter_output_values["provider_response"] = last_json
            except Exception as exc:
                self._log(f"GET generation failed: {exc}")
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            with suppress(Exception):
                self._log(f"GET payload attempt #{attempt + 1}: {_json.dumps(last_json, indent=2)}")

            status = self._extract_status(last_json) or "running"
            is_complete = self._is_complete(last_json)
            attempt += 1
            self._log(f"Polling attempt #{attempt} status={status}")

            # Check for explicit failure statuses
            if status.lower() in {"failed", "error"}:
                self._log(f"Generation failed with status: {status}")
                self.parameter_output_values["video_url"] = None
                # Extract error details from the response
                error_details = self._extract_error_details(last_json)
                self._set_status_results(was_successful=False, result_details=error_details)
                return

            if status.lower() in {"succeeded", "success", "completed"} or is_complete:
                self._handle_completion(last_json, generation_id)
                return

            sleep(poll_interval_s)

    def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        try:
            self._log("Downloading video bytes from provider URL")
            video_bytes = self._download_bytes_from_url(extracted_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_bytes = None

        if video_bytes:
            try:
                from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

                filename = (
                    f"seedance_video_{generation_id}.mp4" if generation_id else f"seedance_video_{int(time.time())}.mp4"
                )
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved video to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                self._log(f"Failed to save to static storage: {e}, using provider URL")
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response.

        Args:
            response_json: The JSON response from the API that may contain error information

        Returns:
            A formatted error message string
        """
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        # Try to extract from provider response first (more detailed)
        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        # Fall back to top-level error
        if top_level_error:
            return self._format_top_level_error(top_level_error)

        # Final fallback
        status = self._extract_status(response_json) or "unknown"
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return _json.loads(provider_response)
            except Exception:
                return None
        if isinstance(provider_response, dict):
            return provider_response
        return None

    def _format_provider_error(
        self, parsed_provider_response: dict[str, Any] | None, top_level_error: Any
    ) -> str | None:
        """Format error message from parsed provider response."""
        if not parsed_provider_response:
            return None

        provider_error = parsed_provider_response.get("error")
        if not provider_error:
            return None

        if isinstance(provider_error, dict):
            error_message = provider_error.get("message", "")
            details = f"{error_message}"

            if error_code := provider_error.get("code"):
                details += f"\nError Code: {error_code}"
            if error_type := provider_error.get("type"):
                details += f"\nError Type: {error_type}"
            if top_level_error:
                details = f"{top_level_error}\n\n{details}"
            return details

        error_msg = str(provider_error)
        if top_level_error:
            return f"{top_level_error}\n\nProvider error: {error_msg}"
        return f"Generation failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"Generation failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"Generation failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["result"] = None
        self.parameter_output_values["status"] = "error"
        self.parameter_output_values["video_url"] = None

    @staticmethod
    def _extract_status(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        for key in ("status", "state", "phase"):
            val = obj.get(key)
            if isinstance(val, str):
                return val
        # Some providers nest status under data/result
        data = obj.get("data") if isinstance(obj, dict) else None
        if isinstance(data, dict):
            for key in ("status", "state", "phase"):
                val = data.get(key)
                if isinstance(val, str):
                    return val
        return None

    @staticmethod
    def _is_complete(obj: dict[str, Any] | None) -> bool:
        if not isinstance(obj, dict):
            return False
        # Direct completion indicators
        if obj.get("result") not in (None, {}):
            return True
        # Check provider response
        if SeedanceVideoGeneration._is_provider_complete(obj):
            return True
        # Timestamps that often signal completion
        for key in ("finished_at", "completed_at", "end_time"):
            if obj.get(key):
                return True
        return False

    @staticmethod
    def _is_provider_complete(prov: Any) -> bool:
        if not isinstance(prov, dict):
            return False
        for key in ("output", "outputs", "data", "task_result"):
            if prov.get(key) not in (None, {}):
                return True
        status = None
        for key in ("status", "state", "phase", "task_status"):
            val = prov.get(key)
            if isinstance(val, str):
                status = val.lower()
                break
        return status in {"succeeded", "success", "completed"}

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        # Heuristic search for a URL in common places
        # 1) direct fields
        for key in ("url", "video_url", "output_url"):
            val = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(val, str) and val.startswith("http"):
                return val
        # 2) nested known containers (Seedance returns content.video_url)
        for key in ("result", "data", "output", "outputs", "content", "task_result"):
            nested = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(nested, dict):
                url = SeedanceVideoGeneration._extract_video_url(nested)
                if url:
                    return url
            elif isinstance(nested, list):
                for item in nested:
                    url = SeedanceVideoGeneration._extract_video_url(item if isinstance(item, dict) else None)
                    if url:
                        return url
        return None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
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
        except Exception:  # noqa: S110
            pass

        return None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            import requests
        except Exception as exc:  # pragma: no cover
            msg = "Missing optional dependency 'requests'. Add it to library dependencies."
            raise ImportError(msg) from exc

        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception:  # pragma: no cover
            return None
        else:
            return resp.content
