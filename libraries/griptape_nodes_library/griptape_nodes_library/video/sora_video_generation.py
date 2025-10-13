from __future__ import annotations

import logging
import os
import time
from contextlib import suppress
from time import monotonic, sleep
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger(__name__)

__all__ = ["SoraVideoGeneration"]

# HTTP error status code threshold
HTTP_ERROR_STATUS = 400

# Size options for different models
SIZE_OPTIONS = {
    "sora-2": ["1280x720", "720x1280"],
    "sora-2-pro": ["1280x720", "720x1280", "1024x1792", "1792x1024"],
}


class SoraVideoGeneration(DataNode):
    """Generate a video using Sora 2 models via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (required)
        - model (str): Model to use (default: sora-2, options: sora-2, sora-2-pro)
        - seconds (int): Clip duration in seconds (optional, options: 4, 6, 8)
        - size (str): Output resolution as widthxheight (default: 720x1280)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Sora 2 through Griptape Cloud model proxy"

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
                tooltip="Text prompt describing the video to generate",
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
                name="model",
                input_types=["str"],
                type="str",
                default_value="sora-2",
                tooltip="Sora model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model",
                },
                traits={Options(choices=["sora-2", "sora-2-pro"])},
            )
        )

        self.add_parameter(
            Parameter(
                name="seconds",
                input_types=["int"],
                type="int",
                default_value=4,
                tooltip="Clip duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[4, 6, 8])},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="720x1280",
                tooltip="Output resolution as widthxheight (options vary by model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SIZE_OPTIONS["sora-2"])},
                ui_options={"display_name": "Size"},
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

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options based on model selection."""
        if parameter.name == "model" and value in SIZE_OPTIONS:
            new_choices = SIZE_OPTIONS[value]
            current_size = self.get_parameter_value("size")

            # If current size is not in new choices, set to default
            if current_size not in new_choices:
                default_size = "720x1280" if "720x1280" in new_choices else new_choices[0]
                self._update_option_choices("size", new_choices, default_size)
            else:
                # Keep current size but update available choices
                self._update_option_choices("size", new_choices, current_size)

        return super().after_value_set(parameter, value)

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        # Get parameters and validate API key
        params = self._get_parameters()
        api_key = self._validate_api_key()
        headers = {"Authorization": f"Bearer {api_key}"}

        # Build and submit request
        generation_id = self._submit_request(params, headers)
        if not generation_id:
            self.parameter_output_values["video_url"] = None
            return

        # Poll for result
        self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        seconds_value = self.get_parameter_value("seconds")
        if isinstance(seconds_value, list):
            seconds_value = seconds_value[0] if seconds_value else None

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "sora-2",
            "seconds": seconds_value,
            "size": self.get_parameter_value("size") or "720x1280",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model']}")

        # Build JSON payload
        json_data = {
            "prompt": params["prompt"],
            "model": params["model"],
            "size": params["size"],
        }

        if params["seconds"]:
            json_data["seconds"] = str(params["seconds"])

        self._log(f"Submitting request to proxy model={params['model']}")
        self._log(f"POST {post_url}")
        self._log(f"JSON payload: {json_data}")
        self._log(f"JSON payload types: {[(k, type(v).__name__, v) for k, v in json_data.items()]}")

        # Make request with JSON data
        post_resp = requests.post(post_url, json=json_data, headers=headers, timeout=60)

        if post_resp.status_code >= HTTP_ERROR_STATUS:
            self._set_safe_defaults()
            self._log(f"Proxy POST error status={post_resp.status_code} body={post_resp.text}")
            msg = f"{self.name} Proxy POST error: {post_resp.status_code} - {post_resp.text}"
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
                self._log("Polling timed out waiting for result")
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()

                content_type = get_resp.headers.get("content-type", "").lower()

                # Check if we got the binary video data
                if "application/octet-stream" in content_type:
                    self._log("Received video data")
                    self._handle_video_completion(get_resp.content)
                    return

                # Otherwise, parse JSON status response
                last_json = get_resp.json()
            except Exception as exc:
                self._log(f"GET generation failed: {exc}")
                msg = f"{self.name} GET generation failed: {exc}"
                raise RuntimeError(msg) from exc

            try:
                status = last_json.get("status", "running") if last_json else "running"
            except Exception:
                status = "running"

            attempt += 1
            self._log(f"Polling attempt #{attempt} status={status}")

            # Check if status indicates completion or failure
            if status and isinstance(status, str):
                status_lower = status.lower()
                if status_lower in {"failed", "error"}:
                    self._log(f"Generation failed with status: {status}")
                    self.parameter_output_values["video_url"] = None
                    return

            sleep(poll_interval_s)

    def _handle_video_completion(self, video_bytes: bytes) -> None:
        """Handle completion when video data is received."""
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            return

        try:
            filename = f"sora_video_{int(time.time())}.mp4"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved video to static storage as {filename}")
        except Exception as e:
            self._log(f"Failed to save video: {e}")
            self.parameter_output_values["video_url"] = None

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
