from __future__ import annotations

import asyncio
import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingMotionControl"]

# Constants
MAX_PROMPT_LENGTH = 2500
HTTP_CLIENT_ERROR_STATUS = 400


class KlingMotionControl(SuccessFailureNode):
    """Generate a video using Kling Motion Control via Griptape Cloud model proxy.

    The Motion Control model transfers character actions from a reference video to a reference image,
    creating a new video where the character in the image performs the actions from the video.

    Inputs:
        - prompt (str): Text prompt for additional guidance (optional, max 2500 chars)
        - reference_image (ImageArtifact|ImageUrlArtifact): Reference image with character (required)
        - reference_video (VideoUrlArtifact): Reference video with actions to transfer (required)
        - keep_original_sound (bool): Keep original video sound (default: True)
        - character_orientation (str): Character orientation - image or video (required)
        - mode (str): Video generation mode - std (Standard) or pro (Professional) (required)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved video URL
        - kling_video_id (str): The video ID from Kling AI
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

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
                name="prompt",
                default_value="",
                tooltip="Optional text prompt for additional motion guidance (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Optional: Add additional control with a text prompt...",
                    "display_name": "prompt",
                },
            )
        )

        # Image Input Group
        with ParameterGroup(name="Reference Image") as image_group:
            # Use PublicArtifactUrlParameter for image upload handling
            self._public_image_url_parameter = PublicArtifactUrlParameter(
                node=self,
                artifact_url_parameter=Parameter(
                    name="reference_image",
                    input_types=["ImageArtifact", "ImageUrlArtifact"],
                    type="ImageUrlArtifact",
                    tooltip="Reference image with character (required). Supports .jpg/.jpeg/.png, max 10MB.",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ),
                disclaimer_message="The Kling Motion Control service utilizes this URL to access the image for generation.",
            )
            self._public_image_url_parameter.add_input_parameters()
        self.add_node_element(image_group)

        # Video Reference Group
        with ParameterGroup(name="Reference Video") as video_group:
            # Use PublicArtifactUrlParameter for video upload handling
            self._public_video_url_parameter = PublicArtifactUrlParameter(
                node=self,
                artifact_url_parameter=Parameter(
                    name="reference_video",
                    input_types=["VideoUrlArtifact"],
                    type="VideoUrlArtifact",
                    tooltip="Reference video with actions to transfer (required). Supports .mp4/.mov, max 100MB.",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ),
                disclaimer_message="The Kling Motion Control service utilizes this URL to access the video for generation.",
            )
            self._public_video_url_parameter.add_input_parameters()

            Parameter(
                name="keep_original_sound",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Keep original video sound",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "keep original sound"},
            )
        video_group.ui_options = {"hide": False}
        self.add_node_element(video_group)

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterString(
                name="character_orientation",
                default_value="video",
                tooltip="Character orientation: 'image' matches image orientation (max 10s video), 'video' matches video orientation (max 30s video)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["image", "video"])},
                ui_options={"display_name": "character orientation"},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode: 'std' (Standard - cost-effective), 'pro' (Professional - higher quality)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
        self.add_node_element(gen_settings_group)

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

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The video ID from Kling AI",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    async def aprocess(self) -> None:
        try:
            await self._process()
        finally:
            # Always cleanup uploaded artifacts
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_video_url_parameter.delete_uploaded_artifact()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()
        logger.info("%s starting motion control generation", self.name)

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
        logger.debug("%s parameters: prompt_length=%d", self.name, len(params["prompt"]))

        # Validate prompt length
        if len(params["prompt"]) > MAX_PROMPT_LENGTH:
            self._set_safe_defaults()
            error_msg = f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(params['prompt'])})."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: prompt too long", self.name)
            return

        # Validate required image
        if not params["image_url"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a reference image."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: missing reference image", self.name)
            return

        # Validate required video
        if not params["video_url"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a reference video."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: missing reference video", self.name)
            return

        # Build payload
        payload = await self._build_payload_async(params)

        # Submit request
        try:
            generation_id = await self._submit_request_async("kling:motion-control", payload, headers)
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
        """Get and process all parameters, including public URLs for image and video."""
        # Get image parameter - use PublicArtifactUrlParameter to get public URL
        reference_image_param = self.get_parameter_value("reference_image")
        image_url = None
        if reference_image_param:
            image_url = self._public_image_url_parameter.get_public_url_for_parameter()

        # Get video parameter - use PublicArtifactUrlParameter to get public URL
        reference_video_param = self.get_parameter_value("reference_video")
        video_url = None
        if reference_video_param:
            video_url = self._public_video_url_parameter.get_public_url_for_parameter()

        keep_sound = self.get_parameter_value("keep_original_sound")
        if keep_sound is None:
            keep_sound = True

        return {
            "prompt": (self.get_parameter_value("prompt") or "").strip(),
            "image_url": image_url,
            "video_url": video_url,
            "keep_original_sound": "yes" if keep_sound else "no",
            "character_orientation": self.get_parameter_value("character_orientation") or "video",
            "mode": self.get_parameter_value("mode") or "pro",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request_async(self, model_id: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        # Use the model ID directly (already includes modality)
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
        """Build the request payload for Kling Motion Control API."""
        payload: dict[str, Any] = {
            "image_url": params["image_url"],
            "video_url": params["video_url"],
            "keep_original_sound": params["keep_original_sound"],
            "character_orientation": params["character_orientation"],
            "mode": params["mode"],
        }

        # Add optional prompt if provided
        if params["prompt"]:
            payload["prompt"] = params["prompt"]

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
        # Extract error details using comprehensive extraction
        error_details = self._extract_error_details(status_json)
        logger.error("%s generation %s: %s", self.name, status.lower(), error_details)
        self.parameter_output_values["video_url"] = None
        self._set_status_results(was_successful=False, result_details=error_details)

    async def _handle_completion_async(self, response_json: dict[str, Any], generation_id: str) -> None:
        """Handle successful completion by downloading and saving the video.

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
                filename = f"kling_motion_control_{generation_id}.mp4"
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

    def _extract_error_details(self, response_json: dict[str, Any]) -> str:  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Extract detailed error message from API response.

        The v2 API provides errors in multiple possible locations:
        1. error + details (JSON string with nested error info)
        2. status_detail.details (JSON string with nested error info)
        3. status_detail.error (top-level error message)
        4. provider_response.error (provider-specific error)
        5. error (top-level error field)
        """
        if not response_json:
            return f"{self.name}: Generation failed with no error details"

        # Check for top-level 'details' field, which may be a JSON string
        details_str = response_json.get("details")
        if details_str and isinstance(details_str, str):
            try:
                details_obj = _json.loads(details_str)
                if isinstance(details_obj, dict):
                    # Handles {"code": ..., "message": ...}
                    error_message = details_obj.get("message")
                    if error_message:
                        msg = f"{self.name}: {error_message}"
                        error_code = details_obj.get("code")
                        if error_code:
                            msg += f" (Error Code: {error_code})"
                        return msg

                    # Handles {"error": {"message": ...}}
                    error_info = details_obj.get("error", {})
                    if isinstance(error_info, dict):
                        error_message = error_info.get("message", "")
                        error_code = error_info.get("code", "")
                        if error_message:
                            msg = f"{self.name}: {error_message}"
                            if error_code:
                                msg += f" (Error Code: {error_code})"
                            return msg
            except (_json.JSONDecodeError, ValueError):
                pass  # Fall through to other checks

        # Check v2 API status_detail first
        status_detail = response_json.get("status_detail")
        if status_detail and isinstance(status_detail, dict):
            # Try to parse details field (often a JSON string)
            details_str = status_detail.get("details")
            if details_str and isinstance(details_str, str):
                try:
                    details_obj = _json.loads(details_str)
                    if isinstance(details_obj, dict):
                        # Handles {"code": ..., "message": ...}
                        error_message = details_obj.get("message")
                        if error_message:
                            msg = f"{self.name}: {error_message}"
                            error_code = details_obj.get("code")
                            if error_code:
                                msg += f" (Error Code: {error_code})"
                            return msg

                        # Handles {"error": {"message": ...}}
                        error_info = details_obj.get("error", {})
                        if isinstance(error_info, dict):
                            error_message = error_info.get("message", "")
                            error_code = error_info.get("code", "")
                            if error_message:
                                msg = f"{self.name}: {error_message}"
                                if error_code:
                                    msg += f" (Error Code: {error_code})"
                                return msg
                except (_json.JSONDecodeError, ValueError):
                    pass

            # Fall back to top-level error in status_detail
            top_error = status_detail.get("error")
            if top_error:
                return f"{self.name}: Generation failed - {top_error}"

        # Check provider_response
        provider_response = response_json.get("provider_response")
        if provider_response:
            if isinstance(provider_response, str):
                with suppress(_json.JSONDecodeError, ValueError):
                    provider_response = _json.loads(provider_response)

            if isinstance(provider_response, dict):
                provider_error = provider_response.get("error")
                if isinstance(provider_error, dict):
                    error_msg = provider_error.get("message", "")
                    error_code = provider_error.get("code", "")
                    if error_msg:
                        msg = f"{self.name}: {error_msg}"
                        if error_code:
                            msg += f" (Error Code: {error_code})"
                        return msg

        # Check top-level error field
        top_level_error = response_json.get("error")
        if top_level_error:
            if isinstance(top_level_error, dict):
                error_msg = top_level_error.get("message", str(top_level_error))
                return f"{self.name}: {error_msg}"
            return f"{self.name}: {top_level_error!s}"

        # Final fallback
        return f"{self.name}: Generation failed with no error details provided"

    def _extract_error_from_initial_response(self, response_json: dict[str, Any]) -> str:
        """Extract error details from initial POST response."""
        return self._extract_error_details(response_json)

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["kling_video_id"] = ""

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

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate API key before workflow starts."""
        exceptions = []

        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            exceptions.append(KeyError(f"{self.name}: {self.API_KEY_NAME} is not configured"))

        return exceptions if exceptions else None
