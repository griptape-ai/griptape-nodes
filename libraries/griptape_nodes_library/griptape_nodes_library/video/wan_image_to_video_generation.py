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
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["WanImageToVideoGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model options with their constraints
MODEL_OPTIONS = [
    "wan2.5-i2v-preview",
    "wan2.2-i2v-flash",
    "wan2.2-i2v-plus",
    "wanx2.1-i2v-plus",
    "wanx2.1-i2v-turbo",
]

# Model-specific configurations
MODEL_CONFIGS = {
    "wan2.5-i2v-preview": {
        "resolutions": ["480P", "720P", "1080P"],
        "durations": [5, 10],
        "supports_audio": True,
        "max_prompt_length": 2000,
    },
    "wan2.2-i2v-flash": {
        "resolutions": ["480P", "720P"],
        "durations": [5],
        "supports_audio": False,
        "max_prompt_length": 800,
    },
    "wan2.2-i2v-plus": {
        "resolutions": ["480P", "1080P"],
        "durations": [5],
        "supports_audio": False,
        "max_prompt_length": 800,
    },
    "wanx2.1-i2v-plus": {
        "resolutions": ["720P"],
        "durations": [5],
        "supports_audio": False,
        "max_prompt_length": 800,
    },
    "wanx2.1-i2v-turbo": {
        "resolutions": ["480P", "720P"],
        "durations": [3, 4, 5],
        "supports_audio": False,
        "max_prompt_length": 800,
    },
}

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"
STATUS_REQUEST_MODERATED = "Request Moderated"
STATUS_CONTENT_MODERATED = "Content Moderated"


class WanImageToVideoGeneration(SuccessFailureNode):
    """Generate videos from images using WAN models via Griptape model proxy.

    Documentation: https://www.alibabacloud.com/help/en/model-studio/image-to-video-api-reference

    Inputs:
        - model (str): WAN model to use (default: "wan2.5-i2v-preview")
            wan2.5-i2v-preview: Supports 480P/720P/1080P, 5-10s duration, audio, 2000 char prompts
            wan2.2-i2v-flash: Supports 480P/720P, 5s duration, 50% faster than 2.1
            wan2.2-i2v-plus: Supports 480P/1080P, 5s duration, improved stability
            wanx2.1-i2v-plus: Supports 720P, 5s duration
            wanx2.1-i2v-turbo: Supports 480P/720P, 3-5s duration
        - input_image (ImageArtifact): Input image for video generation (required)
            Supports JPG, JPEG, PNG, BMP, WEBP
            Resolution: 360-2000 pixels (width and height)
            Size: Max 10 MB
        - prompt (str): Text description of desired video elements (optional)
            Max length varies by model (800-2000 characters)
        - negative_prompt (str): Description of content to avoid (max 500 characters)
        - resolution (str): Output video resolution (model-dependent)
        - duration (int): Video duration in seconds (model-dependent)
        - audio (bool): Auto-generate audio for video (only for wan2.5-i2v-preview, default: True)
        - prompt_extend (bool): Enable intelligent prompt rewriting (default: False)
        - watermark (bool): Add "AI-generated" watermark (default: False)
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
        self.description = "Generate videos from images using WAN models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="wan2.5-i2v-preview",
                tooltip="Select the WAN image-to-video model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Input image parameter (required)
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="Input image for video generation (JPG, PNG, BMP, WEBP; 360-2000Px; max 10MB)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Prompt parameter (optional)
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Text description of desired video elements (max 800-2000 characters depending on model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video elements you want...",
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
                    "placeholder_text": "Describe what you don't want in the video...",
                    "display_name": "Negative Prompt",
                },
            )
        )

        # Resolution parameter
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="1080P",
                tooltip="Output video resolution (available options depend on selected model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_CONFIGS["wan2.5-i2v-preview"]["resolutions"])},
            )
        )

        # Duration parameter
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=5,
                tooltip="Video duration in seconds (model-dependent)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[3, 4, 5, 10])},
            )
        )

        # Audio auto-generation parameter (only for wan2.5-i2v-preview)
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Auto-generate audio for video (only for wan2.5-i2v-preview)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide_property": self._should_hide_audio()},
            )
        )

        # Prompt extend parameter
        self.add_parameter(
            Parameter(
                name="prompt_extend",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable intelligent prompt rewriting to improve generation quality",
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
                tooltip="Add 'AI-generated' watermark in lower-right corner",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Initialize SeedParameter component (at the bottom of input parameters)
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

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _should_hide_audio(self) -> bool:
        """Determine if audio parameter should be hidden based on model selection."""
        model = self.get_parameter_value("model")
        if not model:
            return False
        return model != "wan2.5-i2v-preview"

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes."""
        super().after_value_set(parameter, value)

        # Update parameters when model changes
        if parameter.name == "model" and value in MODEL_CONFIGS:
            model_config = MODEL_CONFIGS[value]

            # Update audio parameter visibility
            if self._should_hide_audio():
                self.hide_parameter_by_name("audio")
            else:
                self.show_parameter_by_name("audio")

            # Update resolution choices
            current_resolution = self.get_parameter_value("resolution")
            new_resolutions = model_config["resolutions"]
            if current_resolution in new_resolutions:
                self._update_option_choices("resolution", new_resolutions, current_resolution)
            else:
                # Set to first available resolution if current is not supported
                self._update_option_choices("resolution", new_resolutions, new_resolutions[0])

            # Update duration choices
            current_duration = self.get_parameter_value("duration")
            new_durations = model_config["durations"]
            if current_duration in new_durations:
                self._update_option_choices("duration", new_durations, current_duration)
            else:
                # Set to first available duration if current is not supported
                self._update_option_choices("duration", new_durations, new_durations[0])

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        try:
            params = self._get_parameters()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        model = params["model"]
        logger.info("Generating video from image with %s", model)

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

    def _get_parameters(self) -> dict[str, Any]:
        model = self.get_parameter_value("model")
        input_image = self.get_parameter_value("input_image")
        resolution = self.get_parameter_value("resolution")
        duration = self.get_parameter_value("duration")

        # Validate input image is provided
        if not input_image:
            msg = "Input image is required for image-to-video generation"
            raise ValueError(msg)

        # Validate model-specific constraints
        model_config = MODEL_CONFIGS.get(model, MODEL_CONFIGS["wan2.5-i2v-preview"])

        # Validate resolution
        if resolution not in model_config["resolutions"]:
            msg = f"{model} does not support resolution {resolution}. Available resolutions: {', '.join(model_config['resolutions'])}"
            raise ValueError(msg)

        # Validate duration
        if duration not in model_config["durations"]:
            msg = f"{model} does not support duration {duration}s. Available durations: {', '.join(str(d) for d in model_config['durations'])}s"
            raise ValueError(msg)

        # Validate audio parameter
        if self.get_parameter_value("audio") and not model_config["supports_audio"]:
            msg = f"{model} does not support audio. Only wan2.5-i2v-preview supports audio parameter."
            raise ValueError(msg)

        return {
            "model": model,
            "input_image": input_image,
            "prompt": self.get_parameter_value("prompt") or "",
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "resolution": resolution,
            "duration": duration,
            "audio": self.get_parameter_value("audio"),
            "seed": self._seed_parameter.get_seed(),
            "prompt_extend": self.get_parameter_value("prompt_extend"),
            "watermark": self.get_parameter_value("watermark"),
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any] | None:
        payload = await self._build_payload(params)
        proxy_url = urljoin(self._proxy_base, f"models/{params['model']}")

        logger.info("Submitting request to Griptape model proxy with %s", params["model"])

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
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(msg) from e
        except Exception as e:
            logger.error("Request failed: %s", e)
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        return response_json

    async def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        # Process input image to base64 data URI
        img_url = await self._process_input_image(params["input_image"])
        if not img_url:
            msg = "Failed to process input image"
            raise ValueError(msg)

        # Build flattened payload (all params at top level)
        payload = {
            "model": params["model"],
            "img_url": img_url,
            "resolution": params["resolution"],
            "duration": params["duration"],
            "prompt_extend": params["prompt_extend"],
            "watermark": params["watermark"],
            "seed": params["seed"],
        }

        # Add optional parameters if provided
        if params["prompt"]:
            payload["prompt"] = params["prompt"]

        if params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"]

        # Add audio parameter (only for wan2.5-i2v-preview)
        if params["model"] == "wan2.5-i2v-preview":
            payload["audio"] = params["audio"]

        return payload

    async def _process_input_image(self, image_input: Any) -> str | None:
        """Process input image and convert to base64 data URI."""
        if not image_input:
            return None

        # Extract string value from input
        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        return await self._convert_to_base64_data_uri(image_value)

    def _extract_image_value(self, image_input: Any) -> str | None:
        """Extract string value from various image input types."""
        if isinstance(image_input, str):
            return image_input

        try:
            # ImageUrlArtifact: .value holds URL string
            if hasattr(image_input, "value"):
                value = getattr(image_input, "value", None)
                if isinstance(value, str):
                    return value

            # ImageArtifact: .base64 holds raw or data-URI
            if hasattr(image_input, "base64"):
                b64 = getattr(image_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception as e:
            logger.error("Failed to extract image value: %s", e)

        return None

    async def _convert_to_base64_data_uri(self, image_value: str) -> str | None:
        """Convert image value to base64 data URI."""
        # If it's already a data URI, return it
        if image_value.startswith("data:image/"):
            return image_value

        # If it's a URL, download and convert to base64
        if image_value.startswith(("http://", "https://")):
            return await self._download_and_encode_image(image_value)

        # Assume it's raw base64 without data URI prefix
        return f"data:image/png;base64,{image_value}"

    async def _download_and_encode_image(self, url: str) -> str | None:
        """Download image from URL and encode as base64 data URI."""
        try:
            image_bytes = await self._download_bytes_from_url(url)
            if image_bytes:
                import base64

                b64_string = base64.b64encode(image_bytes).decode("utf-8")
                return f"data:image/png;base64,{b64_string}"
        except Exception as e:
            logger.error("Failed to download image from URL %s: %s", url, e)
        return None

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
                filename = f"wan_i2v_{int(time.time())}.mp4"
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
