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
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingVideoExtension"]

# Constants
MAX_PROMPT_LENGTH = 2500
HTTP_CLIENT_ERROR_STATUS = 400


class KlingVideoExtension(SuccessFailureNode):
    """Extend an existing video using Kling AI via Griptape Cloud model proxy.

    Extends videos by 4-5 seconds. Maximum total video length: 3 minutes.

    Inputs:
        - video_id (str): Video ID from previous Kling AI generation (required)
        - prompt (str): Text prompt for video extension (max 2500 chars)
        - negative_prompt (str): Negative text prompt (max 2500 chars)
        - cfg_scale (float): Flexibility in video generation (0-1)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved extended video URL
        - kling_video_id (str): The Kling AI video ID
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

        # Basic Settings Group
        with ParameterGroup(name="Basic Settings") as basic_group:
            ParameterString(
                name="video_id",
                tooltip="Video ID from previous Kling AI video generation (required)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Enter video ID from previous Kling generation..."},
            )
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Text prompt for video extension (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe how to continue the video..."},
            )
            ParameterString(
                name="negative_prompt",
                default_value="",
                tooltip="Negative text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe what you don't want..."},
            )
        self.add_node_element(basic_group)

        # Extension Settings Group
        with ParameterGroup(name="Extension Settings") as extension_group:
            ParameterFloat(
                name="cfg_scale",
                default_value=0.5,
                tooltip="Flexibility (0-1). Higher value = lower flexibility, stronger prompt relevance.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(extension_group)

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
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved extended video as URL artifact",
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
            result_details_tooltip="Details about the video extension result or any errors",
            result_details_placeholder="Extension status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:  # noqa: PLR0911
        # Clear execution status at the start
        self._clear_execution_status()
        logger.info("%s starting video extension", self.name)

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
            "%s parameters: video_id=%s, cfg_scale=%s",
            self.name,
            params["video_id"],
            params["cfg_scale"],
        )

        # Validate video_id is provided
        if not params["video_id"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a video_id from a previous Kling AI generation."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no video_id provided", self.name)
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

        # Build payload
        payload = self._build_payload(params)

        # Submit request - using static model ID "kling:video-extend"
        try:
            generation_id = await self._submit_request_async("kling:video-extend", payload, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with extension.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result_async(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "video_id": (self.get_parameter_value("video_id") or "").strip(),
            "prompt": self.get_parameter_value("prompt") or "",
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "cfg_scale": self.get_parameter_value("cfg_scale") or 0.5,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request_async(self, model_id: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        # Use the static model ID directly (already includes modality)
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

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for Kling video extension API."""
        payload: dict[str, Any] = {
            "video_id": params["video_id"],
            "cfg_scale": float(params["cfg_scale"]),
        }

        # Add prompts if provided
        if params["prompt"]:
            payload["prompt"] = params["prompt"].strip()

        if params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"].strip()

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
            result_details="Video extension timed out after 1200 seconds waiting for result.",
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
            error_msg = f"Extension completed but failed to fetch result: {exc}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(RuntimeError(error_msg))
            return

        try:
            result_json = result_resp.json()
        except (ValueError, _json.JSONDecodeError) as exc:
            logger.error("%s received invalid JSON in result: %s", self.name, exc)
            error_msg = f"Extension completed but received invalid JSON: {exc}"
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
                message = f"Extension {status.lower()} with no details provided"
        else:
            message = f"Extension {status.lower()} with no details provided"

        logger.error("%s extension %s: %s", self.name, status.lower(), message)
        self.parameter_output_values["video_url"] = None
        self._set_status_results(
            was_successful=False, result_details=f"{self.name} extension {status.lower()}: {message}"
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
                result_details=f"{self.name} extension completed but no videos found in response.",
            )
            return

        video_info = videos[0]
        download_url = video_info.get("url")
        video_id = video_info.get("id")

        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} extension completed but no download URL found in response.",
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
                filename = f"kling_video_extension_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("%s saved video to static storage as %s", self.name, filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video extended successfully and saved as {filename}."
                )
            except (OSError, PermissionError) as e:
                logger.warning("%s failed to save to static storage: %s, using provider URL", self.name, e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video extended successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video extended successfully. Using provider URL (could not download video bytes).",
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
