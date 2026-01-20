from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingOmniVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
HTTP_CLIENT_ERROR_STATUS = 400
MAX_IMAGES_WITH_VIDEO = 4
MAX_IMAGES_WITHOUT_VIDEO = 7
MAX_IMAGES_FOR_END_FRAME = 2


class KlingOmniVideoGeneration(SuccessFailureNode):
    """Generate a video using Kling Omni AI via Griptape Cloud model proxy.

    The Omni model supports various capabilities through templated prompts with elements,
    images, and videos. Use <<<element_1>>>, <<<image_1>>>, <<<video_1>>> in prompts.

    Inputs:
        - prompt (str): Text prompt with optional templates (max 2500 chars, required)
        - reference_images (list[ImageArtifact]): Reference images for generation (optional)
        - first_frame_image (ImageArtifact|ImageUrlArtifact|str): First frame image (optional)
        - end_frame_image (ImageArtifact|ImageUrlArtifact|str): End frame image (optional)
        - element_ids (str): Comma-separated element IDs (optional)
        - reference_video (VideoUrlArtifact): Reference video for editing or style reference (optional, max 1)
        - video_refer_type (str): Video reference type (base: edit video, feature: use as feature reference)
        - video_keep_sound (bool): Keep original video sound (default: False)
        - mode (str): Video generation mode (std: Standard, pro: Professional)
        - aspect_ratio (str): Aspect ratio (required when not using first frame or video editing)
        - duration (int): Video length in seconds (3-10s)
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
                tooltip="Text prompt with optional templates like <<<image_1>>>, <<<element_1>>> (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the video... Use <<<image_1>>> to reference images.",
            )
        )

        # Image Inputs Group
        self.add_parameter(
            Parameter(
                name="first_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="First frame image (optional). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "first frame"},
            )
        )
        self.add_parameter(
            Parameter(
                name="end_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="End frame image (optional). Requires first frame to be set.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "end frame"},
            )
        )
        self.add_parameter(
            ParameterList(
                name="reference_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                    "list[str]",
                ],
                default_value=[],
                tooltip="Reference images for generation. These appear first in the template (<<<image_1>>>, <<<image_2>>>, etc.)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "reference images"},
            )
        )

        # Advanced References Group
        with ParameterGroup(name="Advanced References") as advanced_group:
            ParameterString(
                name="element_ids",
                default_value="",
                tooltip="Comma-separated element IDs (e.g., '123,456,789')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "e.g., 123,456,789", "hide": True},
            )
        advanced_group.ui_options = {"hide": False}
        self.add_node_element(advanced_group)

        # Use PublicArtifactUrlParameter for video upload handling
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Reference video for editing or style reference (optional, max 1)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/video.mp4"},
            ),
            disclaimer_message="The Kling Omni service utilizes this URL to access the video for generation.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterString(
                name="video_refer_type",
                default_value="base",
                tooltip="Video reference type: 'feature' is the feature reference video, 'base' is the video to be edited",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["base", "feature"])},
            )
            Parameter(
                name="video_keep_sound",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Keep original video sound (only applies when video_refer_type is 'base')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "keep video sound"},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode (std: Standard, pro: Professional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
            ParameterString(
                name="aspect_ratio",
                default_value="16:9",
                tooltip="Aspect ratio (required when not using first frame or video editing)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16", "1:1"])},
            )
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video length in seconds (3-10s). Only 5/10s for text-to-video and first-frame generation.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[3, 4, 5, 6, 7, 8, 9, 10])},
            )
        self.add_node_element(gen_settings_group)

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

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The video ID from Kling AI",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The Kling AI video ID",
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
            # Always cleanup uploaded video artifact
            self._public_video_url_parameter.delete_uploaded_artifact()

    async def _process(self) -> None:  # noqa: C901, PLR0911, PLR0912, PLR0915
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
            "%s parameters: prompt_length=%d, duration=%s", self.name, len(params["prompt"]), params["duration"]
        )

        # Validate prompt is provided
        if not params["prompt"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a prompt to generate video."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: empty prompt", self.name)
            return

        # Validate prompt length
        if len(params["prompt"]) > MAX_PROMPT_LENGTH:
            self._set_safe_defaults()
            error_msg = f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (limit: {MAX_PROMPT_LENGTH})."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: prompt too long", self.name)
            return

        # Parse element IDs from comma-separated string
        element_list = []
        if params["element_ids"]:
            try:
                element_ids_parts = [part.strip() for part in params["element_ids"].split(",") if part.strip()]
                element_list = [{"element_id": int(eid)} for eid in element_ids_parts]
            except ValueError:
                self._set_safe_defaults()
                error_msg = f"{self.name} validation failed: element_ids must be comma-separated integers"
                self._set_status_results(was_successful=False, result_details=error_msg)
                logger.error("%s validation failed: invalid element_ids", self.name)
                return

        # Build video list from individual video parameters
        video_list = []
        if params["reference_video_url"]:
            keep_sound_str = "yes" if params["video_keep_sound"] else "no"
            video_list.append(
                {
                    "video_url": params["reference_video_url"],
                    "refer_type": params["video_refer_type"],
                    "keep_original_sound": keep_sound_str,
                }
            )

        # Get reference images (already a list from ParameterList)
        ref_images_input = params["reference_images"]
        if not isinstance(ref_images_input, list):
            ref_images_input = [ref_images_input] if ref_images_input else []

        # Validate end frame requires first frame
        if params["end_frame_image"] and not params["first_frame_image"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} end_frame_image requires first_frame_image to be set."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: end frame without first frame", self.name)
            return

        # Count total images and elements
        total_image_count = len(ref_images_input)
        if params["first_frame_image"]:
            total_image_count += 1
        if params["end_frame_image"]:
            total_image_count += 1
        total_element_count = len(element_list)
        has_video = len(video_list) > 0

        # Validate image + element count limits
        if has_video:
            if total_image_count + total_element_count > MAX_IMAGES_WITH_VIDEO:
                self._set_safe_defaults()
                error_msg = (
                    f"{self.name} when using reference videos, the sum of images ({total_image_count}) "
                    f"and elements ({total_element_count}) cannot exceed {MAX_IMAGES_WITH_VIDEO}."
                )
                self._set_status_results(was_successful=False, result_details=error_msg)
                logger.error("%s validation failed: too many images+elements with video", self.name)
                return
        elif total_image_count + total_element_count > MAX_IMAGES_WITHOUT_VIDEO:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name} the sum of images ({total_image_count}) "
                f"and elements ({total_element_count}) cannot exceed {MAX_IMAGES_WITHOUT_VIDEO}."
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: too many images+elements", self.name)
            return

        # Validate end frame not allowed with >2 images
        if params["end_frame_image"] and total_image_count > MAX_IMAGES_FOR_END_FRAME:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name} end frame is not supported when there are more than {MAX_IMAGES_FOR_END_FRAME} images."
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: end frame with >2 images", self.name)
            return

        # Validate video editing cannot be used with first/end frames
        has_base_video = any(v.get("refer_type") == "base" for v in video_list if isinstance(v, dict))
        if has_base_video and (params["first_frame_image"] or params["end_frame_image"]):
            self._set_safe_defaults()
            error_msg = f"{self.name} video editing (refer_type='base') cannot be used with first or end frame images."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: video editing with first/end frames", self.name)
            return

        # Validate duration constraints for text/first-frame generation
        is_text_or_first_frame = not has_base_video
        if is_text_or_first_frame and params["duration"] not in [5, 10]:
            self._set_safe_defaults()
            error_msg = (
                f"{self.name} text-to-video and first-frame generation only support 5 or 10 second durations "
                f"(got {params['duration']}s)."
            )
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: invalid duration for text/first-frame generation", self.name)
            return

        # Build payload
        payload = await self._build_payload_async(params)

        # Submit request - using static model ID "kling-video-o1:omnivideo"
        try:
            generation_id = await self._submit_request_async("kling-video-o1:omnivideo", payload, headers)
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
        # Get video parameters - use PublicArtifactUrlParameter to get public URL
        reference_video_param = self.get_parameter_value("reference_video")
        reference_video_url = None
        if reference_video_param:
            reference_video_url = self._public_video_url_parameter.get_public_url_for_parameter()

        video_keep_sound = self.get_parameter_value("video_keep_sound")
        if video_keep_sound is None:
            video_keep_sound = False

        return {
            "prompt": (self.get_parameter_value("prompt") or "").strip(),
            "reference_images": self.get_parameter_value("reference_images") or [],
            "first_frame_image": await self._prepare_image_data_url_async(
                self.get_parameter_value("first_frame_image")
            ),
            "end_frame_image": await self._prepare_image_data_url_async(self.get_parameter_value("end_frame_image")),
            "element_ids": (self.get_parameter_value("element_ids") or "").strip(),
            "reference_video_url": reference_video_url,
            "video_refer_type": self.get_parameter_value("video_refer_type") or "base",
            "video_keep_sound": video_keep_sound,
            "mode": self.get_parameter_value("mode") or "pro",
            "aspect_ratio": self.get_parameter_value("aspect_ratio") or "16:9",
            "duration": self.get_parameter_value("duration") or 5,
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

    async def _build_payload_async(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
        """Build the request payload for Kling Omni API.

        Images are ordered: reference images FIRST, then start/end frames at the END.
        This allows users to reference <<<image_1>>>, <<<image_2>>> in the order they
        supplied the reference images.
        """
        payload: dict[str, Any] = {
            "model_name": "kling-video-o1",
            "prompt": params["prompt"],
            "mode": params["mode"],
            "aspect_ratio": params["aspect_ratio"],
            "duration": int(params["duration"]),
        }

        # Build image_list array: reference images FIRST, then start/end frames at END
        image_list = []

        # Add reference images first (so they are image_1, image_2, etc. in order)
        # Reference images don't have a "type" field
        ref_images_input = params.get("reference_images", [])
        if not isinstance(ref_images_input, list):
            ref_images_input = [ref_images_input] if ref_images_input else []

        for ref_image in ref_images_input:
            if ref_image:
                ref_image_url = await self._prepare_image_data_url_async(ref_image)
                if ref_image_url:
                    image_list.append({"image_url": ref_image_url})

        # Add start and end frames at the END with explicit type field
        if params["first_frame_image"]:
            image_list.append({"image_url": params["first_frame_image"], "type": "first_frame"})
        if params["end_frame_image"]:
            image_list.append({"image_url": params["end_frame_image"], "type": "end_frame"})

        if image_list:
            payload["image_list"] = image_list

        # Parse element IDs from comma-separated string
        if params.get("element_ids"):
            element_list = []
            try:
                element_ids_parts = [part.strip() for part in params["element_ids"].split(",") if part.strip()]
                element_list = [{"element_id": int(eid)} for eid in element_ids_parts]
            except ValueError:
                pass  # Validation already happened in _process
            if element_list:
                payload["element_list"] = element_list

        # Add video if provided
        if params.get("reference_video_url"):
            keep_sound_str = "yes" if params.get("video_keep_sound", False) else "no"
            payload["video_list"] = [
                {
                    "video_url": params["reference_video_url"],
                    "refer_type": params.get("video_refer_type", "base"),
                    "keep_original_sound": keep_sound_str,
                }
            ]

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
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("Image URL converted to data URI for proxy")
                return b64

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:
            try:
                from copy import deepcopy

                red = deepcopy(b)
                # Redact data URLs in image_list
                if "image_list" in red and isinstance(red["image_list"], list):
                    for img in red["image_list"]:
                        if isinstance(img, dict) and "image_url" in img:
                            img_url = img["image_url"]
                            if isinstance(img_url, str) and img_url.startswith("data:image/"):
                                parts = img_url.split(",", 1)
                                header = parts[0] if parts else "data:image/"
                                b64 = parts[1] if len(parts) > 1 else ""
                                img["image_url"] = f"{header},<redacted base64 length={len(b64)}>"
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
                filename = f"kling_omni_video_{generation_id}.mp4"
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
