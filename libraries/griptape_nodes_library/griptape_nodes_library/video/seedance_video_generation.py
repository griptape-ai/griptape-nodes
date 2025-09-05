from __future__ import annotations

import os
import logging
import time
from time import sleep, monotonic
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode, AsyncResult
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact
from griptape_nodes.traits.options import Options
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ["SeedanceVideoGeneration"]


class SeedanceVideoGeneration(DataNode):
    """
    Generate a video using the Seedance model via Griptape Cloud Forwarders.

    Inputs:
        - prompt (str): Text prompt (you can include provider flags like --resolution)
        - model_id (str): Provider model id (default: seedance-1-0-pro-250528)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim provider response from the initial POST
        - video_url (VideoUrlArtifact): Saved static video URL
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    # Base URL is derived from env var and joined with /api/ at runtime

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        try:
            self.category = "API Nodes"
            self.description = "Generate video via Seedance through Griptape Cloud forwarder"

            # Compute API base once
            base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
            base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
            api_base = urljoin(base_slash, "api/")
            self._forwarders_base = urljoin(api_base, "forwarders/")

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
                    tooltip="Model id to call via forwarder",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    ui_options={
                        "display_name": "Model ID",
                        "hide": True,
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
                    traits={Options(choices=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"])}
                )
            )

            # Duration (seconds)
            self.add_parameter(
                Parameter(
                    name="duration",
                    input_types=["int", "str"],
                    type="int",
                    default_value=5,
                    tooltip="Video duration in seconds",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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

            # OUTPUTS
            self.add_parameter(
                Parameter(
                    name="generation_id",
                    output_type="str",
                    tooltip="Griptape Cloud generation id",
                    allowed_modes={ParameterMode.OUTPUT}
                )
            )

            self.add_parameter(
                Parameter(
                    name="provider_response",
                    output_type="dict",
                    type="dict",
                    tooltip="Verbatim response from provider (initial POST)",
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
                    ui_options={"is_full_width": True},
                )
            )
        except Exception as exc:
            logger.exception("SeedanceVideoGeneration __init__ setup failed: %s", exc)
            raise

    def _log(self, message: str) -> None:
        try:
            logger.info(message)
        except Exception:
            pass

        # No separate status message panel; we'll stream updates to the 'status' output
        # Always polls with fixed interval/timeout

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:  # noqa: C901 - keeping logic clear and linear
        try:
            import requests  # optional dependency, installed via library metadata
        except Exception as exc:  # pragma: no cover - surfaced to UI
            self._set_safe_defaults()
            raise ImportError(
                "Missing optional dependency 'requests'. Add it to library dependencies."
            ) from exc

        prompt: str = self.get_parameter_value("prompt") or ""
        model_id: str = self.get_parameter_value("model_id") or "seedance-1-0-pro-250528"
        resolution: str = self.get_parameter_value("resolution") or "1080p"
        ratio: str = self.get_parameter_value("ratio") or "16:9"
        first_frame_input = self.get_parameter_value("first_frame")
        duration_val = self.get_parameter_value("duration")
        camerafixed_val = self.get_parameter_value("camerafixed")
        poll_interval_s: float = 5.0
        timeout_s: float = 600.0

        api_key: Optional[str] = self.get_config_value(service=self.SERVICE_NAME, value=self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            raise ValueError(f"Missing {self.API_KEY_NAME}. Ensure it's set in the environment/config.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        post_url = urljoin(self._forwarders_base, f"models/{model_id}")

        # Build content array with flags added to text
        text_parts: list[str] = [prompt.strip()]
        if resolution:
            text_parts.append(f"--resolution {resolution}")
        if ratio:
            text_parts.append(f"--ratio {ratio}")
        if duration_val is not None and str(duration_val).strip():
            text_parts.append(f"--duration {str(int(duration_val)).strip()}")
        if camerafixed_val is not None:
            cam_str = "true" if bool(camerafixed_val) else "false"
            text_parts.append(f"--camerafixed {cam_str}")
        text_payload = "  ".join([p for p in text_parts if p])

        content_list: list[Dict[str, Any]] = [{"type": "text", "text": text_payload}]

        # Coerce first frame to URL or data URI if provided
        first_frame_url = self._coerce_image_url_or_data_uri(first_frame_input)
        # If it's an external URL, inline to data URI so forwarder doesn't need to fetch
        if isinstance(first_frame_url, str) and first_frame_url.startswith(("http://", "https://")):
            try:
                import base64
                rff = requests.get(first_frame_url, timeout=20)
                rff.raise_for_status()
                ct = (rff.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not ct.startswith("image/"):
                    ct = "image/jpeg"
                b64 = base64.b64encode(rff.content).decode("utf-8")
                first_frame_url = f"data:{ct};base64,{b64}"
                self._log("First frame URL converted to data URI for forwarder")
            except Exception as _e:
                self._log(f"Warning: failed to inline first frame URL: {_e}")
        if first_frame_url:
            content_list.append({
                "type": "image_url",
                "image_url": {"url": first_frame_url},
            })

        payload: Dict[str, Any] = {
            "provider_request": {
                "model": model_id,
                "content": content_list,
            }
        }

        # Log sanitized request
        def _sanitize_body(b: Dict[str, Any]) -> Dict[str, Any]:
            try:
                from copy import deepcopy
                red = deepcopy(b)
                cont = red.get("provider_request", {}).get("content", [])
                for it in cont:
                    if isinstance(it, dict) and it.get("type") == "image_url":
                        iu = it.get("image_url") or {}
                        url = iu.get("url")
                        if isinstance(url, str) and url.startswith("data:image/"):
                            parts = url.split(",", 1)
                            header = parts[0] if parts else "data:image/"
                            b64 = parts[1] if len(parts) > 1 else ""
                            iu["url"] = f"{header},<redacted base64 length={len(b64)}>"
                return red
            except Exception:
                return b

        self._log(f"Submitting request to forwarder model={model_id}")
        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        try:
            import json as _json
            self._log(f"POST {post_url}\nheaders={dbg_headers}\nbody={_json.dumps(_sanitize_body(payload), indent=2)}")
        except Exception:
            pass

        post_resp = requests.post(post_url, json=payload, headers=headers, timeout=60)
        if post_resp.status_code >= 400:
            self._set_safe_defaults()
            try:
                self._log(f"Forwarder POST error status={post_resp.status_code} headers={dict(post_resp.headers)} body={post_resp.text}")
            except Exception:
                self._log("Forwarder POST error (non-text body)")
            raise RuntimeError(f"POST to forwarder failed: {post_resp.status_code}")
        post_json: Dict[str, Any] = post_resp.json()

        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response
        init_status = self._extract_status(post_json)
        if init_status:
            self._log(f"Initial status: {init_status}")

        if generation_id:
            self._log(f"Submitted. generation_id={generation_id}")
            # UI status param removed; console logging only
        else:
            self._log("No generation_id returned from POST response")
            

        if not generation_id:
            self.parameter_output_values["result"] = None
            self.parameter_output_values["video_url"] = None
            return

        # Poll for final result
        get_url = urljoin(self._forwarders_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json: Optional[Dict[str, Any]] = None

        attempt = 0
        while True:
            if monotonic() - start_time > timeout_s:
                
                self.parameter_output_values["video_url"] = self._extract_video_url(last_json)
                self._log("Polling timed out waiting for result")
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()
                last_json = get_resp.json()
            except Exception as exc:  # pragma: no cover
                # Leave the last good state and surface error
                self._log(f"GET generation failed: {exc}")
                
                raise RuntimeError(f"GET generation failed: {exc}") from exc

            # Log full payload for diagnostics each attempt
            try:
                import json as _json
                self._log(f"GET payload attempt #{attempt + 1}: {_json.dumps(last_json, indent=2)}")
            except Exception:
                pass

            status = self._extract_status(last_json) or "running"
            is_complete = self._is_complete(last_json)
            attempt += 1
            self._log(f"Polling attempt #{attempt} status={status}")

            if status.lower() in {"succeeded", "success", "completed", "failed", "error"} or is_complete:
                # Try to fetch and store the video in static files immediately
                extracted_url = self._extract_video_url(last_json)

                if extracted_url:
                    # Attempt download
                    try:
                        self._log("Downloading video bytes from provider URL")
                        video_bytes = self._download_bytes_from_url(extracted_url)
                    except Exception:
                        video_bytes = None

                    if video_bytes:
                        # Try to save to static files
                        try:
                            from griptape_nodes import GriptapeNodes
                            filename = f"seedance_video_{int(time.time())}.mp4"
                            static_files_manager = GriptapeNodes.StaticFilesManager()
                            saved_url = static_files_manager.save_static_file(video_bytes, filename)
                            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                            self._log(f"Saved video to static storage as {filename}")
                        except Exception:
                            # Fallback to provider URL artifact if saving fails
                            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
                    else:
                        # No bytes downloaded; fallback to provider URL artifact
                        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
                # End terminal
                return

            sleep(poll_interval_s)

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["result"] = None
        self.parameter_output_values["status"] = "error"
        self.parameter_output_values["video_url"] = None

    @staticmethod
    def _extract_status(obj: Optional[Dict[str, Any]]) -> Optional[str]:
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
        # Provider response often carries status
        prov = obj.get("provider_response") if isinstance(obj, dict) else None
        if isinstance(prov, dict):
            for key in ("status", "state", "phase", "task_status"):
                val = prov.get(key)
                if isinstance(val, str):
                    return val
        return None

    @staticmethod
    def _is_complete(obj: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(obj, dict):
            return False
        # Direct completion indicators
        if obj.get("result") not in (None, {}):
            return True
        # Provider response may include outputs or task_result
        prov = obj.get("provider_response")
        if isinstance(prov, dict):
            for key in ("output", "outputs", "data", "task_result"):
                if prov.get(key) not in (None, {}):
                    return True
            status = None
            for key in ("status", "state", "phase", "task_status"):
                val = prov.get(key)
                if isinstance(val, str):
                    status = val.lower()
                    break
            if status in {"succeeded", "success", "completed"}:
                return True
        # Timestamps that often signal completion
        for key in ("finished_at", "completed_at", "end_time"):
            if obj.get(key):
                return True
        return False

    @staticmethod
    def _extract_video_url(obj: Optional[Dict[str, Any]]) -> Optional[str]:
        if not obj:
            return None
        # Heuristic search for a URL in common places
        # 1) direct fields
        for key in ("url", "video_url", "output_url"):
            val = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(val, str) and val.startswith("http"):
                return val
        # 2) nested known containers (Seedance returns provider_response.content.video_url)
        for key in ("result", "data", "output", "outputs", "content", "provider_response", "task_result"):
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
    def _coerce_image_url_or_data_uri(val: Any) -> Optional[str]:
        if val is None:
            return None
        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            if v.startswith("http://") or v.startswith("https://") or v.startswith("data:image/"):
                return v
            # Assume raw base64 without header; default to png
            return f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://") or v.startswith("data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                if b64.startswith("data:image/"):
                    return b64
                return f"data:image/png;base64,{b64}"
        except Exception:
            return None
        return None

    @staticmethod
    def _download_bytes_from_url(url: str) -> Optional[bytes]:
        try:
            import requests
        except Exception as exc:  # pragma: no cover
            raise ImportError(
                "Missing optional dependency 'requests'. Add it to library dependencies."
            ) from exc

        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except Exception:  # pragma: no cover
            return None


