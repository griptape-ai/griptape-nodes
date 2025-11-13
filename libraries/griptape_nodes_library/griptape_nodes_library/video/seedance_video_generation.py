from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from time import monotonic, sleep
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedanceVideoGeneration"]


class SeedanceVideoGeneration(SuccessFailureNode):
    """Generate a video using the Seedance model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (supports provider flags like --resolution)
        - model_id (str): Provider model id (default: seedance-1-0-pro-250528)
        - resolution (str): Output resolution (default: 1080p, options: 480p, 720p, 1080p)
        - ratio (str): Output aspect ratio (default: 16:9, options: 16:9, 4:3, 1:1, 3:4, 9:16, 21:9)
        - duration (int): Video duration in seconds (default: 5, options: 5, 10)
        - camerafixed (bool): Camera fixed flag (default: False)
        - first_frame (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (URL or base64 data URI)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for i2v model (URL or base64 data URI)
        (Always polls for result: 5s interval, 10 min timeout)

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
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for the video (supports provider flags)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "Prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="seedance-1-0-pro-250528",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model ID",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "seedance-1-0-pro-250528",
                            "seedance-1-0-pro-fast-251015",
                            "seedance-1-0-lite-t2v-250428",
                            "seedance-1-0-lite-i2v-250428",
                        ]
                    )
                },
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="1080p",
                tooltip="Output resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["480p", "720p", "1080p"])},
            )
        )

        # Aspect ratio selection
        self.add_parameter(
            Parameter(
                name="ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"])},
            )
        )

        # Duration in seconds
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=5,
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
        )

        # Camera fixed flag
        self.add_parameter(
            Parameter(
                name="camerafixed",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Camera fixed",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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
                tooltip="Verbatim response from API (initial POST)",
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

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        if parameter.name == "model_id":
            # Show last_frame parameter only for i2v model
            show_last_frame = value == "seedance-1-0-lite-i2v-250428"
            if show_last_frame:
                self.show_parameter_by_name("last_frame")
            else:
                self.hide_parameter_by_name("last_frame")

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
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": self.get_parameter_value("model_id") or "seedance-1-0-pro-250528",
            "resolution": self.get_parameter_value("resolution") or "1080p",
            "ratio": self.get_parameter_value("ratio") or "16:9",
            "first_frame": self.get_parameter_value("first_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "duration": self.get_parameter_value("duration"),
            "camerafixed": self.get_parameter_value("camerafixed"),
        }

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
        # Build text payload with flags
        text_parts = [params["prompt"].strip()]
        if params["resolution"]:
            text_parts.append(f"--resolution {params['resolution']}")
        if params["ratio"]:
            text_parts.append(f"--ratio {params['ratio']}")
        if params["duration"] is not None and str(params["duration"]).strip():
            text_parts.append(f"--duration {str(int(params['duration'])).strip()}")
        if params["camerafixed"] is not None:
            cam_str = "true" if bool(params["camerafixed"]) else "false"
            text_parts.append(f"--camerafixed {cam_str}")

        text_payload = "  ".join([p for p in text_parts if p])
        content_list: list[dict[str, Any]] = [{"type": "text", "text": text_payload}]

        # Add frame images based on model capabilities
        self._add_frame_images(content_list, params)

        return {"model": params["model_id"], "content": content_list}

    def _add_frame_images(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frame images to content list based on model capabilities."""
        model_id = params["model_id"]

        if model_id == "seedance-1-0-pro-250528":
            self._add_first_frame_only(content_list, params)
        elif model_id == "seedance-1-0-lite-i2v-250428":
            self._add_i2v_frames(content_list, params)
        # Add other model handling here as needed

    def _add_first_frame_only(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add first frame for models that only support single frame input."""
        frame_url = self._prepare_frame_url(params["first_frame"])
        if frame_url:
            content_list.append({"type": "image_url", "image_url": {"url": frame_url}})

    def _add_i2v_frames(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frames for image-to-video models that support first and last frames."""
        has_last_frame = params["last_frame"] is not None

        # Add first frame
        first_frame_url = self._prepare_frame_url(params["first_frame"])
        if first_frame_url:
            if has_last_frame:
                # When both frames present, add role identifiers
                content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
            else:
                # When only first frame, no role needed
                content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}})

        # Add last frame if provided
        if has_last_frame:
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
