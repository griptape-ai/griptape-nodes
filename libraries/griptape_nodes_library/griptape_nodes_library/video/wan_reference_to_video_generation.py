from __future__ import annotations

import json
import logging
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
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["WanReferenceToVideoGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model options
MODEL_OPTIONS = [
    "wan2.6-r2v",
]

# Size options organized by resolution tier
SIZE_OPTIONS_720P = [
    "1280*720",  # 16:9
    "720*1280",  # 9:16
    "960*960",   # 1:1
    "1088*832",  # 4:3
    "832*1088",  # 3:4
]

SIZE_OPTIONS_1080P = [
    "1920*1080",  # 16:9
    "1080*1920",  # 9:16
    "1440*1440",  # 1:1
    "1632*1248",  # 4:3
    "1248*1632",  # 3:4
]

ALL_SIZE_OPTIONS = SIZE_OPTIONS_1080P + SIZE_OPTIONS_720P

# Shot type options
SHOT_TYPE_OPTIONS = [
    "single",
    "multi",
]

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"
STATUS_REQUEST_MODERATED = "Request Moderated"
STATUS_CONTENT_MODERATED = "Content Moderated"


class WanReferenceToVideoGeneration(SuccessFailureNode):
    """Generate videos from reference videos using WAN models via Griptape model proxy.

    Creates a new video based on the subject and timbre of reference videos and a prompt.
    Use character1, character2, character3 in the prompt to refer to subjects in
    reference videos 1, 2, 3 respectively.

    Documentation: https://www.alibabacloud.com/help/en/model-studio/reference-to-video-api-reference

    Inputs:
        - model (str): WAN model to use (default: "wan2.6-r2v")
        - prompt (str): Text description using character1/character2/character3 to reference
            subjects in the reference videos (max 1500 characters)
        - negative_prompt (str): Description of content to avoid (max 500 characters)
        - reference_video_1 (VideoUrlArtifact): First reference video (required)
        - reference_video_2 (VideoUrlArtifact): Second reference video (optional)
        - reference_video_3 (VideoUrlArtifact): Third reference video (optional)
            Video requirements: MP4/MOV, 2-30s duration, max 100MB
        - size (str): Output video resolution (default: "1920*1080")
            720p tier: 1280*720, 720*1280, 960*960, 1088*832, 832*1088
            1080p tier: 1920*1080, 1080*1920, 1440*1440, 1632*1248, 1248*1632
        - duration (int): Video duration in seconds (5 or 10, default: 5)
        - shot_type (str): Shot type - "single" or "multi" (default: "single")
        - audio (bool): Auto-generate audio for video (default: True)
        - watermark (bool): Add "AI Generated" watermark (default: False)
        - randomize_seed (bool): If true, randomize the seed on each run
        - seed (int): Random seed for reproducible results (default: 42)

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
        self.description = "Generate videos from reference videos using WAN models via Griptape model proxy"

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
                default_value="wan2.6-r2v",
                tooltip="Select the WAN reference-to-video model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Prompt parameter
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text description using character1/character2/character3 to reference subjects (max 1500 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "character1 is happily watching a movie on the sofa...",
                    "display_name": "Prompt",
                },
            )
        )

        # Negative prompt parameter
        self.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Description of content to avoid (max 500 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "low resolution, error, worst quality...",
                    "display_name": "Negative Prompt",
                },
            )
        )

        # Reference video 1 (required) using PublicArtifactUrlParameter
        self._public_video_url_parameter_1 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_1",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="First reference video (required). MP4/MOV, 2-30s, max 100MB. Use 'character1' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 1"},
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_1.add_input_parameters()

        # Reference video 2 (optional) using PublicArtifactUrlParameter
        self._public_video_url_parameter_2 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_2",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Second reference video (optional). MP4/MOV, 2-30s, max 100MB. Use 'character2' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 2"},
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_2.add_input_parameters()

        # Reference video 3 (optional) using PublicArtifactUrlParameter
        self._public_video_url_parameter_3 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_3",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Third reference video (optional). MP4/MOV, 2-30s, max 100MB. Use 'character3' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 3"},
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_3.add_input_parameters()

        # Size parameter
        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="1920*1080",
                tooltip="Output video resolution (width*height)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=ALL_SIZE_OPTIONS)},
            )
        )

        # Duration parameter
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=5,
                tooltip="Video duration in seconds (5 or 10)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
        )

        # Shot type parameter
        self.add_parameter(
            Parameter(
                name="shot_type",
                input_types=["str"],
                type="str",
                default_value="single",
                tooltip="Shot type: 'single' for continuous shot, 'multi' for multiple changing shots",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SHOT_TYPE_OPTIONS)},
            )
        )

        # Audio parameter
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Auto-generate audio for video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Watermark parameter
        self.add_parameter(
            Parameter(
                name="watermark",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Add 'AI Generated' watermark in lower-right corner",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Initialize SeedParameter component
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
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
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        reference_video_1 = self.get_parameter_value("reference_video_1")
        if not reference_video_1:
            exceptions.append(ValueError("Reference Video 1 must be provided"))
        prompt = self.get_parameter_value("prompt")
        if not prompt:
            exceptions.append(ValueError("Prompt must be provided"))
        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Get parameters
        try:
            params = self._get_parameters()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        model = params["model"]
        logger.info("Generating video from reference with %s", model)

        # Submit request and get synchronous response
        try:
            response = await self._submit_request(params, headers)
            if not response:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No response returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            # HTTP error during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Handle synchronous response
        await self._handle_response(response)

        # Cleanup uploaded artifacts
        self._public_video_url_parameter_1.delete_uploaded_artifact()
        self._public_video_url_parameter_2.delete_uploaded_artifact()
        self._public_video_url_parameter_3.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:
        model = self.get_parameter_value("model")
        prompt = self.get_parameter_value("prompt")
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        size = self.get_parameter_value("size")
        duration = self.get_parameter_value("duration")
        shot_type = self.get_parameter_value("shot_type")
        audio = self.get_parameter_value("audio")
        watermark = self.get_parameter_value("watermark")

        # Collect reference video URLs
        reference_video_urls = []
        video_url_1 = self._public_video_url_parameter_1.get_public_url_for_parameter()
        if video_url_1:
            reference_video_urls.append(video_url_1)

        video_url_2 = self._public_video_url_parameter_2.get_public_url_for_parameter()
        if video_url_2:
            reference_video_urls.append(video_url_2)

        video_url_3 = self._public_video_url_parameter_3.get_public_url_for_parameter()
        if video_url_3:
            reference_video_urls.append(video_url_3)

        if not reference_video_urls:
            msg = "At least one reference video URL is required"
            raise ValueError(msg)

        # Validate size
        if size not in ALL_SIZE_OPTIONS:
            msg = f"Invalid size {size}. Available sizes: {', '.join(ALL_SIZE_OPTIONS)}"
            raise ValueError(msg)

        # Validate duration
        if duration not in [5, 10]:
            msg = f"Invalid duration {duration}s. Available durations: 5, 10"
            raise ValueError(msg)

        # Validate shot_type
        if shot_type not in SHOT_TYPE_OPTIONS:
            msg = f"Invalid shot_type {shot_type}. Available options: {', '.join(SHOT_TYPE_OPTIONS)}"
            raise ValueError(msg)

        return {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "reference_video_urls": reference_video_urls,
            "size": size,
            "duration": duration,
            "shot_type": shot_type,
            "audio": audio,
            "watermark": watermark,
            "seed": self._seed_parameter.get_seed(),
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any] | None:
        payload = self._build_payload(params)
        proxy_url = urljoin(self._proxy_base, f"models/{params['model']}")

        logger.info("Submitting request to Griptape model proxy with %s", params["model"])

        # Log sanitized payload (truncate prompt)
        sanitized_prompt = params["prompt"]
        if len(sanitized_prompt) > PROMPT_TRUNCATE_LENGTH:
            sanitized_prompt = sanitized_prompt[:PROMPT_TRUNCATE_LENGTH] + "..."
        logger.info("Request with prompt: %s", sanitized_prompt)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(proxy_url, json=payload, headers=headers, timeout=300)
                response.raise_for_status()
                response_json = response.json()
                logger.info("Request submitted successfully")
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error: %s - %s", e.response.status_code, e.response.text)
            # Try to parse error response body
            try:
                error_json = e.response.json()
                error_msg = error_json.get("error", "")
                provider_response = error_json.get("provider_response", "")
                msg_parts = [p for p in [error_msg, provider_response] if p]
                msg = " - ".join(msg_parts) if msg_parts else self._extract_error_details(error_json)
            except Exception:
                msg = f"API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(msg) from e
        except Exception as e:
            logger.error("Request failed: %s", e)
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        return response_json

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        # Build payload matching proxy expected format
        payload = {
            "model": params["model"],
            "prompt": params["prompt"],
            "reference_video_urls": params["reference_video_urls"],
            "size": params["size"],
            "duration": params["duration"],
            "shot_type": params["shot_type"],
            "audio": params["audio"],
            "watermark": params["watermark"],
            "seed": params["seed"],
        }

        # Add negative prompt if provided
        if params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"]

        return payload

    async def _handle_response(self, response: dict[str, Any]) -> None:
        """Handle WAN synchronous response and extract video.

        Response shape:
        {
            "task_id": "...",
            "task_status": "SUCCEEDED",
            "video_url": "https://...",
            "submit_time": "...",
            "scheduled_time": "...",
            "end_time": "...",
            "orig_prompt": "..."
        }
        """
        self.parameter_output_values["provider_response"] = response

        # Extract task_id for generation_id
        task_id = response.get("task_id", "")
        self.parameter_output_values["generation_id"] = str(task_id)

        # Extract task status and video URL from top-level fields
        task_status = response.get("task_status")

        # Check task status
        if task_status != "SUCCEEDED":
            logger.error("Generation failed with task_status: %s", task_status)
            self._set_safe_defaults()
            error_details = self._extract_error_details(response)
            self._set_status_results(was_successful=False, result_details=error_details)
            return

        video_url = response.get("video_url")
        if video_url:
            await self._save_video_from_url(video_url)
        else:
            logger.warning("No video_url found in response")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )

    async def _save_video_from_url(self, video_url: str) -> None:
        """Download and save the video from the provided URL."""
        try:
            logger.info("Downloading video from URL")
            video_bytes = await self._download_bytes_from_url(video_url)
            if video_bytes:
                filename = f"wan_r2v_{int(time.time())}.mp4"
                from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("Saved video to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            else:
                self._set_status_results(
                    was_successful=False,
                    result_details="Video generation completed but could not download video bytes from URL.",
                )
        except Exception as e:
            logger.error("Failed to save video from URL: %s", e)
            self._set_status_results(
                was_successful=False,
                result_details=f"Video generation completed but could not save to static storage: {e}",
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

        # Check for status-based errors
        status = response_json.get("status")

        # Handle moderation specifically
        if status in [STATUS_REQUEST_MODERATED, STATUS_CONTENT_MODERATED]:
            return self._format_moderation_error(response_json)

        # Handle other failure statuses
        if status in [STATUS_FAILED, STATUS_ERROR]:
            return self._format_failure_status_error(response_json, status)

        # Final fallback
        return f"Generation failed.\n\nFull API response:\n{response_json}"

    def _format_moderation_error(self, response_json: dict[str, Any]) -> str:
        """Format error message for moderated content."""
        details = response_json.get("details", {})
        moderation_reasons = details.get("Moderation Reasons", [])
        if moderation_reasons:
            reasons_str = ", ".join(moderation_reasons)
            return f"Content was moderated and blocked.\nModeration Reasons: {reasons_str}"
        return "Content was moderated and blocked by safety filters."

    def _format_failure_status_error(self, response_json: dict[str, Any], status: str) -> str:
        """Format error message for failed/error status."""
        result = response_json.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return f"Generation failed: {result['error']}"
        return f"Generation failed with status '{status}'."

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
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
