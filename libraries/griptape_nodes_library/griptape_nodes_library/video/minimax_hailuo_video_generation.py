from __future__ import annotations

import base64
import json as _json
import logging
import os
from contextlib import suppress
from copy import deepcopy
from time import monotonic, sleep
from typing import Any, ClassVar
from urllib.parse import urljoin

import requests
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["MinimaxHailuoVideoGeneration"]


class MinimaxHailuoVideoGeneration(SuccessFailureNode):
    """Generate a video using the MiniMax Hailuo model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Provider model id (default: MiniMax-Hailuo-2.3)
        - duration (int): Video duration in seconds (default: 6, options depend on model)
        - resolution (str): Output resolution (options depend on model and duration)
        - prompt_optimizer (bool): Enable prompt optimization (default: False)
        - fast_pretreatment (bool): Reduce optimization time for 2.3/02 models (default: False)
        - first_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (data URL)
        - last_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for 02 model (data URL)
        (Always polls for result: 5s interval, 10 min timeout)

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
        "MiniMax-Hailuo-2.3": {
            "durations": [6, 10],
            "resolutions": {"6": ["768P", "1080P"], "10": ["768P"]},
            "default_resolution": {"6": "768P", "10": "768P"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-02": {
            "durations": [6, 10],
            "resolutions": {"6": ["768P", "1080P"], "10": ["768P"]},
            "default_resolution": {"6": "768P", "10": "768P"},
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-2.3-Fast": {
            "durations": [6],
            "resolutions": {"6": ["720P", "1080P"]},
            "default_resolution": {"6": "720P"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": False,
        },
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via MiniMax Hailuo through Griptape Cloud model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="MiniMax-Hailuo-2.3",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "MiniMax-Hailuo-2.3 (TTV & ITV)",
                            "MiniMax-Hailuo-02 (TTV & ITV)",
                            "MiniMax-Hailuo-2.3-Fast (ITV)",
                        ]
                    )
                },
            )
        )

        # Duration in seconds
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=6,
                tooltip="Video duration in seconds (options depend on model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[6, 10])},
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="768P",
                tooltip="Output resolution (options depend on model and duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720P", "768P", "1080P"])},
            )
        )

        # Prompt optimizer flag
        self.add_parameter(
            Parameter(
                name="prompt_optimizer",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable prompt optimization",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Fast pretreatment flag (only for 2.3 and 02 models)
        self.add_parameter(
            Parameter(
                name="fast_pretreatment",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Reduce optimization time (only for MiniMax-Hailuo-2.3 and MiniMax-Hailuo-02)",
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
                    "Optional last frame image for MiniMax-Hailuo-02 model as data URL (data:image/jpeg;base64,...). "
                    "Supported formats: JPG, JPEG, PNG, WebP. Requirements: <20MB, short edge >300px, "
                    "aspect ratio between 2:5 and 5:2."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame Image", "hide": True},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        if parameter.name == "model_id":
            # Clean model name to remove display hints
            clean_model = self._clean_model_name(value)

            # Show/hide last_frame_image parameter only for 02 model
            capabilities = self.MODEL_CAPABILITIES.get(clean_model, {})
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

        return super().after_value_set(parameter, value)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Get parameters and validate
        params = self._get_parameters()

        # Validate model-specific requirements
        if params["model_id"] == "MiniMax-Hailuo-2.3-Fast" and not params["first_frame_image"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a first frame image for MiniMax-Hailuo-2.3-Fast model (image-to-video only)."
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
            return

        # Build payload
        payload = self._build_payload(params)

        # Submit request
        try:
            generation_id = self._submit_request(params["model_id"], payload, headers)
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
        self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        raw_model_id = self.get_parameter_value("model_id") or "MiniMax-Hailuo-2.3"
        # Strip display hints from model name (e.g., "MiniMax-Hailuo-2.3 (TTV & ITV)" -> "MiniMax-Hailuo-2.3")
        model_id = self._clean_model_name(raw_model_id)

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": model_id,
            "duration": self.get_parameter_value("duration"),
            "resolution": self.get_parameter_value("resolution") or "768P",
            "prompt_optimizer": self.get_parameter_value("prompt_optimizer"),
            "fast_pretreatment": self.get_parameter_value("fast_pretreatment"),
            "first_frame_image": self.get_parameter_value("first_frame_image"),
            "last_frame_image": self.get_parameter_value("last_frame_image"),
        }

    @staticmethod
    def _clean_model_name(model_name: str) -> str:
        """Remove display hints from model name (e.g., ' (TTV & ITV)')."""
        if " (" in model_name:
            return model_name.split(" (")[0]
        return model_name

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, model_id: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{model_id}")

        self._log(f"Submitting request to proxy model={model_id}")
        self._log_request(post_url, headers, payload)

        try:
            post_resp = requests.post(post_url, json=payload, headers=headers, timeout=60)
        except Exception as e:
            self._set_safe_defaults()
            msg = f"{self.name} failed to submit request: {e}"
            raise RuntimeError(msg) from e

        if post_resp.status_code >= 400:  # noqa: PLR2004
            self._set_safe_defaults()
            self._log(
                f"Proxy POST error status={post_resp.status_code} headers={dict(post_resp.headers)} body={post_resp.text}"
            )
            try:
                error_json = post_resp.json()
                error_details = self._extract_error_from_initial_response(error_json)
                msg = f"{self.name} request failed: {error_details}"
            except Exception:
                msg = f"{self.name} request failed: HTTP {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        try:
            post_json = post_resp.json()
        except Exception as e:
            self._set_safe_defaults()
            msg = f"{self.name} received invalid JSON response: {e}"
            raise RuntimeError(msg) from e

        generation_id = str(post_json.get("generation_id") or "")

        if generation_id:
            self._log(f"Submitted. generation_id={generation_id}")
            self.parameter_output_values["generation_id"] = generation_id
        else:
            self._log("No generation_id returned from POST response")

        return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for MiniMax Hailuo API."""
        model_id = params["model_id"]
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": params["prompt"].strip(),
        }

        # Add duration
        if params["duration"] is not None:
            payload["duration"] = int(params["duration"])

        # Add resolution
        if params["resolution"]:
            payload["resolution"] = params["resolution"]

        # Always send prompt_optimizer (defaults to False)
        payload["prompt_optimizer"] = bool(params["prompt_optimizer"])

        # Add fast_pretreatment only for models that support it
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})
        if capabilities.get("supports_fast_pretreatment", False):
            payload["fast_pretreatment"] = bool(params["fast_pretreatment"])

        # Add first_frame_image if provided and model supports it
        if capabilities.get("supports_first_frame", False):
            first_frame_data_url = self._prepare_frame_data_url(params["first_frame_image"])
            if first_frame_data_url:
                payload["first_frame_image"] = first_frame_data_url

        # Add last_frame_image if provided and model supports it
        if capabilities.get("supports_last_frame", False):
            last_frame_data_url = self._prepare_frame_data_url(params["last_frame_image"])
            if last_frame_data_url:
                payload["last_frame_image"] = last_frame_data_url

        return payload

    def _prepare_frame_data_url(self, frame_input: Any) -> str | None:
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
            return self._inline_external_url(frame_url)

        return frame_url

    def _inline_external_url(self, url: str) -> str | None:
        """Download external image URL and convert to data URL."""
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            self._log(f"{self.name} failed to inline frame URL: {e}")
            return None
        else:
            content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
            if not content_type.startswith("image/"):
                content_type = "image/jpeg"
            b64 = base64.b64encode(resp.content).decode("utf-8")
            self._log("Frame URL converted to data URI for proxy")
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
            except Exception:
                return b
            else:
                return red

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
                self.parameter_output_values["video_url"] = None
                self._log(f"{self.name} polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Video generation timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()
                last_json = get_resp.json()
                self.parameter_output_values["provider_response"] = last_json
            except Exception as exc:
                self._log(f"{self.name} GET generation failed: {exc}")
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            with suppress(Exception):
                self._log(f"GET payload attempt #{attempt + 1}: {_json.dumps(last_json, indent=2)}")

            attempt += 1

            # Check for success: file.download_url exists and is populated
            file_obj = last_json.get("file")
            if isinstance(file_obj, dict):
                download_url = file_obj.get("download_url")
                if download_url and isinstance(download_url, str):
                    self._log(f"{self.name} generation succeeded")
                    self._handle_completion(last_json, generation_id)
                    return

            # Check for failure: base_resp.status_msg contains error
            base_resp = last_json.get("base_resp")
            if isinstance(base_resp, dict):
                status_msg = base_resp.get("status_msg")
                if status_msg and status_msg != "success":
                    self._log(f"{self.name} generation failed: {status_msg}")
                    self.parameter_output_values["video_url"] = None
                    self._set_status_results(was_successful=False, result_details=f"{self.name} generation failed: {status_msg}")
                    return

            # Log current state and continue polling
            status = last_json.get("status", "unknown")
            self._log(f"{self.name} polling attempt #{attempt} status={status}")

            # Continue polling for non-terminal states (Preparing, Queueing, Processing)
            sleep(poll_interval_s)

    def _handle_completion(self, response_json: dict[str, Any], generation_id: str) -> None:
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
            self._log(f"{self.name} downloading video from provider URL")
            video_bytes = self._download_bytes_from_url(download_url)
        except Exception as e:
            self._log(f"{self.name} failed to download video: {e}")
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"minimax_hailuo_video_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._log(f"{self.name} saved video to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                self._log(f"{self.name} failed to save to static storage: {e}, using provider URL")
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
        except Exception:  # noqa: S110
            pass

        return None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        """Download file from URL and return bytes."""
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception:
            return None
        else:
            return resp.content
