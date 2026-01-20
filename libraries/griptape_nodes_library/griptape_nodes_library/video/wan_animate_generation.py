from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.video_utils import get_video_duration

logger = logging.getLogger("griptape_nodes")

__all__ = ["WanAnimateGeneration"]

# Model options
MODEL_OPTIONS = [
    "wan2.2-animate-mix",
    "wan2.2-animate-move",
]

# Mode options
MODE_OPTIONS = [
    "wan-std",
    "wan-pro",
]

# HTTP status code threshold for error responses
HTTP_ERROR_STATUS = 400

# Generation status constants
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCELED = "CANCELED"
STATUS_UNKNOWN = "UNKNOWN"


class WanAnimateGeneration(SuccessFailureNode):
    """Generate animated videos from images using WAN Animate models via Griptape model proxy.

    WAN Animate models combine a source image with a reference video to create animations.
    - wan2.2-animate-mix: Combines image with reference video motion
    - wan2.2-animate-move: Animates an image based on reference video motion

    Both models support two service modes:
    - wan-std (standard): Lower cost
    - wan-pro (professional): Higher quality

    Inputs:
        - model (str): WAN Animate model to use (default: "wan2.2-animate-mix")
        - mode (str): Service mode - "wan-std" (standard) or "wan-pro" (professional)
        - image_url (ImageUrlArtifact): Source image to animate (required)
            Format: JPG, JPEG, PNG, BMP, or WEBP
            Dimensions: 200-4096 pixels (width and height), aspect ratio 1:3 to 3:1
            Size: Max 5 MB
            Content: Single person facing camera, complete face, not obstructed
        - video_url (VideoUrlArtifact): Reference video for motion (required)
            Format: MP4, AVI, or MOV
            Duration: 2-30 seconds
            Dimensions: 200-2048 pixels (width and height), aspect ratio 1:3 to 3:1
            Size: Max 200 MB
            Content: Single person facing camera, complete face, not obstructed

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - video (VideoUrlArtifact): Generated video as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate animated videos from images using WAN Animate models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value=MODEL_OPTIONS[0],
                tooltip="Select the WAN Animate model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )
        # Mode selection
        self.add_parameter(
            ParameterString(
                name="mode",
                default_value=MODE_OPTIONS[0],
                tooltip="Service mode: wan-std or wan-pro",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODE_OPTIONS)},
            )
        )
        # Input image URL using PublicArtifactUrlParameter
        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="image_url",
                input_types=["ImageUrlArtifact"],
                type="ImageUrlArtifact",
                default_value="",
                tooltip="Source image to animate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image URL"},
            ),
            disclaimer_message="The WAN Animate service utilizes this URL to access the image for animation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # Reference video URL using PublicArtifactUrlParameter
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="video_url",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Reference video for motion transfer",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Video URL"},
            ),
            disclaimer_message="The WAN Animate service utilizes this URL to access the reference video for motion transfer.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            Parameter(
                name="video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Generated video as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        image_url = self.get_parameter_value("image_url")
        if not image_url:
            exceptions.append(ValueError("Image URL must be provided"))
        video_url = self.get_parameter_value("video_url")
        if not video_url:
            exceptions.append(ValueError("Video URL must be provided"))
        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
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

        # Get parameters
        params = await self._get_parameters()

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Build and submit request
        try:
            generation_id = await self._submit_request(params, headers)
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
        await self._poll_for_result(generation_id, headers, params["duration"])

        # Cleanup uploaded artifacts
        self._public_image_url_parameter.delete_uploaded_artifact()
        self._public_video_url_parameter.delete_uploaded_artifact()

    async def _get_parameters(self) -> dict[str, Any]:
        # Get the original video URL before uploading to calculate duration
        video_param = self.get_parameter_value("video_url")
        original_video_url = video_param.value if hasattr(video_param, "value") else str(video_param)

        # Calculate duration from the original video (ceiling to int)
        duration = math.ceil(await get_video_duration(original_video_url))
        logger.debug("Detected video duration: %ss", duration)

        return {
            "model": self.get_parameter_value("model"),
            "mode": self.get_parameter_value("mode"),
            "image_url": self._public_image_url_parameter.get_public_url_for_parameter(),
            "video_url": self._public_video_url_parameter.get_public_url_for_parameter(),
            "duration": duration,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model']}")
        payload = self._build_payload(params)

        logger.debug("Submitting request to proxy model=%s", params["model"])

        async with httpx.AsyncClient() as client:
            post_resp = await client.post(post_url, json=payload, headers=headers, timeout=60)

        if post_resp.status_code >= HTTP_ERROR_STATUS:
            self._set_safe_defaults()
            logger.debug(
                "Proxy POST error status=%s headers=%s body=%s",
                post_resp.status_code,
                dict(post_resp.headers),
                post_resp.text,
            )
            try:
                error_json = post_resp.json()
                error_msg = error_json.get("error", "")
                provider_response = error_json.get("provider_response", "")
                msg_parts = [p for p in [error_msg, provider_response] if p]
                msg = " - ".join(msg_parts) if msg_parts else self._extract_error_details(error_json)
            except Exception:
                msg = f"Proxy POST error: {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        post_json = post_resp.json()
        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response

        if generation_id:
            logger.debug("Submitted. generation_id=%s", generation_id)
        else:
            logger.debug("No generation_id returned from POST response")

        return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        # Build payload matching proxy expected format
        payload = {
            "input": {
                "image_url": params["image_url"],
                "video_url": params["video_url"],
            },
            "parameters": {
                "mode": params["mode"],
                "duration": params["duration"],
            },
        }

        return payload

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str], video_duration: int) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        pending_start_time = time.monotonic()
        running_start_time = None
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        pending_timeout_s = 30.0
        running_timeout_s = video_duration * 30.0

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    get_resp = await client.get(get_url, headers=headers, timeout=60)
                    get_resp.raise_for_status()
                    last_json = get_resp.json()
                    self.parameter_output_values["provider_response"] = last_json
                except Exception as exc:
                    logger.debug("GET generation failed: %s", exc)
                    error_msg = f"Failed to poll generation status: {exc}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    self._handle_failure_exception(RuntimeError(error_msg))
                    return

                attempt += 1
                status = self._extract_status(last_json) or STATUS_UNKNOWN
                logger.info("Polling attempt #%s status=%s", attempt, status)

                if status == STATUS_PENDING and time.monotonic() - pending_start_time > pending_timeout_s:
                    self.parameter_output_values["video"] = self._extract_video_url(last_json)
                    logger.debug("Polling timed out waiting for generation to start")
                    self._set_status_results(
                        was_successful=False,
                        result_details=f"Video generation timed out after {pending_timeout_s} seconds waiting for generation to start.",
                    )
                    return

                if status == STATUS_RUNNING:
                    if not running_start_time:
                        running_start_time = time.monotonic()
                    if running_start_time and time.monotonic() - running_start_time > running_timeout_s:
                        self.parameter_output_values["video"] = self._extract_video_url(last_json)
                        logger.debug("Polling timed out waiting for result")
                        self._set_status_results(
                            was_successful=False,
                            result_details=f"Video generation timed out after {int(running_timeout_s)} seconds of processing.",
                        )
                        return

                if status in {STATUS_FAILED, STATUS_CANCELED}:
                    provider_resp = last_json.get("provider_response") if last_json else {}
                    error_code = provider_resp.get("code") if isinstance(provider_resp, dict) else None
                    error_message = provider_resp.get("message") if isinstance(provider_resp, dict) else None
                    log_parts = [p for p in [error_code, error_message] if p]
                    logger.error("Generation failed: %s", " - ".join(log_parts) or status)
                    self.parameter_output_values["video"] = None
                    error_details = self._extract_error_details(last_json)
                    self._set_status_results(was_successful=False, result_details=error_details)
                    return

                if status == STATUS_SUCCEEDED:
                    await self._handle_completion(last_json, generation_id)
                    return

                await asyncio.sleep(poll_interval_s)

    async def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        try:
            logger.debug("Downloading video bytes from provider URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            logger.debug("Failed to download video: %s", e)
            video_bytes = None

        if video_bytes:
            try:
                filename = (
                    f"wan_animate_{generation_id}.mp4" if generation_id else f"wan_animate_{int(time.time())}.mp4"
                )
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.debug("Saved video to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                logger.debug("Failed to save to static storage: %s, using provider URL", e)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        if top_level_error:
            return self._format_top_level_error(top_level_error)

        status = self._extract_status(response_json) or STATUS_UNKNOWN
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return json.loads(provider_response)
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
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video"] = None

    @staticmethod
    def _extract_status(response_json: dict[str, Any] | None) -> str | None:
        if not response_json:
            return None
        task_status = response_json.get("task_status")
        if isinstance(task_status, str):
            return task_status
        return None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        results = obj.get("results")
        if isinstance(results, dict):
            video_url = results.get("video_url")
            if isinstance(video_url, str) and video_url.startswith("http"):
                return video_url
        return None

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
