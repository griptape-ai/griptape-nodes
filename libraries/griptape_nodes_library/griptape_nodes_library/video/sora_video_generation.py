from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact, load_pil_from_url

logger = logging.getLogger("griptape_nodes")

__all__ = ["SoraVideoGeneration"]

# HTTP error status code threshold
HTTP_ERROR_STATUS = 400

# Size options for different models
SIZE_OPTIONS = {
    "sora-2": ["1280x720", "720x1280"],
    "sora-2-pro": ["1280x720", "720x1280", "1024x1792", "1792x1024"],
}


class SoraVideoGeneration(SuccessFailureNode):
    """Generate a video using Sora 2 models via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (required)
        - model (str): Model to use (default: sora-2, options: sora-2, sora-2-pro)
        - seconds (int): Clip duration in seconds (optional, options: 4, 6, 8)
        - size (str): Output resolution as widthxheight (default: 720x1280)
        - start_frame (ImageUrlArtifact): Optional starting frame image (auto-updates size if supported)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error

    Note: When a start_frame is provided, the size parameter will automatically update
    to match the image dimensions if they match a supported resolution.
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

        self.add_parameter(
            Parameter(
                name="start_frame",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                tooltip="Optional: Starting frame image (auto-updates size if dimensions are supported)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Start Frame",
                    "clickable_file_browser": True,
                    "expander": True,
                },
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

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options based on model selection and auto-update size from start_frame."""
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

        elif parameter.name == "start_frame" and value:
            # Auto-update size parameter to match image dimensions if supported
            self._auto_update_size_from_image(value)

        return super().after_value_set(parameter, value)

    def _auto_update_size_from_image(self, image_value: Any) -> None:
        """Automatically update the size parameter to match the image dimensions if supported."""
        try:
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                image_value = dict_to_image_url_artifact(image_value)

            if not hasattr(image_value, "value") or not image_value.value:
                return

            # Load PIL image to get dimensions
            pil_image = load_pil_from_url(image_value.value)
            image_size = f"{pil_image.width}x{pil_image.height}"

            # Get available size options for current model
            current_model = self.get_parameter_value("model") or "sora-2"
            available_sizes = SIZE_OPTIONS.get(current_model, SIZE_OPTIONS["sora-2"])

            # If image size matches one of the supported sizes, update the size parameter
            if image_size in available_sizes:
                self.set_parameter_value("size", image_size)
                self._log(f"Auto-updated size to {image_size} to match start_frame dimensions")
            else:
                self._log(
                    f"Start frame size {image_size} not in supported sizes {available_sizes} for model {current_model}"
                )
        except Exception as e:
            self._log(f"Could not auto-update size from image: {e}")

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
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

        headers = {"Authorization": f"Bearer {api_key}"}

        # Build and submit request
        try:
            generation_id = await self._submit_request(params, headers)
            if not generation_id:
                self.parameter_output_values["video_url"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except (RuntimeError, ValueError) as e:
            # HTTP error or validation error (e.g., start frame dimensions) during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        seconds_value = self.get_parameter_value("seconds")
        if isinstance(seconds_value, list):
            seconds_value = seconds_value[0] if seconds_value else None

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "sora-2",
            "seconds": seconds_value,
            "size": self.get_parameter_value("size") or "720x1280",
            "start_frame": self.get_parameter_value("start_frame"),
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _process_start_frame(self, start_frame: Any, expected_size: str) -> str | None:
        """Process start_frame image: validate dimensions and encode to base64.

        Args:
            start_frame: Image artifact or None
            expected_size: Expected size as 'widthxheight' (e.g., '720x1280')

        Returns:
            Base64-encoded image string or None if no start_frame provided

        Raises:
            ValueError: If image dimensions don't match expected size
        """
        if not start_frame:
            return None

        # Convert to ImageUrlArtifact if needed
        if isinstance(start_frame, dict):
            start_frame = dict_to_image_url_artifact(start_frame)

        if not hasattr(start_frame, "value") or not start_frame.value:
            return None

        # Load PIL image
        pil_image = load_pil_from_url(start_frame.value)

        # Parse expected dimensions
        expected_width, expected_height = map(int, expected_size.split("x"))

        # Validate dimensions
        if pil_image.width != expected_width or pil_image.height != expected_height:
            msg = (
                f"Start frame dimensions ({pil_image.width}x{pil_image.height}) must match video size ({expected_size})"
            )
            raise ValueError(msg)

        # Convert to base64
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        base64_string = base64.b64encode(image_bytes).decode("utf-8")

        return base64_string

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model']}")

        # Build JSON payload
        json_data = {
            "prompt": params["prompt"],
            "model": params["model"],
            "size": params["size"],
        }

        if params["seconds"]:
            json_data["seconds"] = str(params["seconds"])

        # Process and add start_frame if provided
        if params["start_frame"]:
            base64_image = self._process_start_frame(params["start_frame"], params["size"])
            if base64_image:
                json_data["input_reference"] = base64_image

        self._log(f"Submitting request to proxy model={params['model']}")
        self._log(f"POST {post_url}")
        self._log(f"JSON payload keys: {list(json_data.keys())}")
        if "input_reference" in json_data:
            self._log("Including start_frame as input_reference")
        self._log(
            f"JSON payload types: {[(k, type(v).__name__, len(v) if k == 'input_reference' else v) for k, v in json_data.items()]}"
        )

        # Make request with JSON data
        async with httpx.AsyncClient() as client:
            post_resp = await client.post(post_url, json=json_data, headers=headers, timeout=60)

        if post_resp.status_code >= HTTP_ERROR_STATUS:
            self._set_safe_defaults()
            self._log(f"Proxy POST error status={post_resp.status_code} body={post_resp.text}")
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

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 600.0

        async with httpx.AsyncClient() as client:
            while True:
                if monotonic() - start_time > timeout_s:
                    self.parameter_output_values["video_url"] = None
                    self._log("Polling timed out waiting for result")
                    self._set_status_results(
                        was_successful=False,
                        result_details=f"Video generation timed out after {timeout_s} seconds waiting for result.",
                    )
                    return

                try:
                    get_resp = await client.get(get_url, headers=headers, timeout=60)
                    get_resp.raise_for_status()

                    content_type = get_resp.headers.get("content-type", "").lower()

                    # Check if we got the binary video data
                    if "application/octet-stream" in content_type:
                        self._log("Received video data")
                        self._handle_video_completion(get_resp.content)
                        return

                    # Otherwise, parse JSON status response
                    last_json = get_resp.json()
                    # Update provider_response with latest polling data
                    self.parameter_output_values["provider_response"] = last_json
                except Exception as exc:
                    self._log(f"GET generation failed: {exc}")
                    error_msg = f"Failed to poll generation status: {exc}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    self._handle_failure_exception(RuntimeError(error_msg))
                    return

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

                        # Extract error details from the response (last_json already set in provider_response)
                        error_details = self._extract_error_details(last_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

                await asyncio.sleep(poll_interval_s)

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
        status = response_json.get("status", "unknown")
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                import json as _json

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

    def _handle_video_completion(self, video_bytes: bytes) -> None:
        """Handle completion when video data is received."""
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details="Received empty video data from API.")
            return

        try:
            filename = f"sora_video_{int(time.time())}.mp4"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved video to static storage as {filename}")
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        except Exception as e:
            self._log(f"Failed to save video: {e}")
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False, result_details=f"Video generation completed but failed to save: {e}"
            )

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
