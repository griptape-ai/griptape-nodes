from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedreamImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model mapping from human-friendly names to API model IDs
MODEL_MAPPING = {
    "seedream-4.5": "seedream-4-5-251128",
    "seedream-4.0": "seedream-4-0-250828",
    "seedream-3.0-t2i": "seedream-3-0-t2i-250415",
    "seededit-3.0-i2i": "seededit-3-0-i2i-250628",
}

# Size options for different models
SIZE_OPTIONS = {
    "seedream-4.5": [
        "2K",
        "4K",
        "2560x1440",
        "1440x2560",
        "3840x2160",
        "2160x3840",
        "4096x2160",
        "2160x4096",
        "4096x4096",
    ],
    "seedream-4.0": [
        "1K",
        "2K",
        "4K",
        "2048x2048",
        "2304x1728",
        "1728x2304",
        "2560x1440",
        "1440x2560",
        "2496x1664",
        "1664x2496",
        "3024x1296",
    ],
    "seedream-3.0-t2i": [
        "2048x2048",
        "2304x1728",
        "1728x2304",
        "2560x1440",
        "1440x2560",
        "2496x1664",
        "1664x2496",
        "3024x1296",
    ],
    "seededit-3.0-i2i": [
        "adaptive",
    ],
}

# Maximum number of input images for models that support multiple images
MAX_IMAGES_PER_MODEL = {
    "seedream-4.5": 14,
    "seedream-4.0": 10,
}


class SeedreamImageGeneration(SuccessFailureNode):
    """Generate images using Seedream models via Griptape model proxy.

    Supports four models:
    - seedream-4.5: Latest model with optional multiple image inputs (up to 14) and shorthand size options (2K, 4K)
      Minimum resolution: 2560x1440, Maximum resolution: 4096x4096
    - seedream-4.0: Advanced model with optional multiple image inputs (up to 10) and shorthand size options (1K, 2K, 4K)
    - seedream-3.0-t2i: Text-to-image only model with explicit size dimensions (WIDTHxHEIGHT format)
    - seededit-3.0-i2i: Image-to-image editing model requiring single input image (WIDTHxHEIGHT format)

    Inputs:
        - model (str): Model selection (seedream-4.5, seedream-4.0, seedream-3.0-t2i, seededit-3.0-i2i)
        - prompt (str): Text prompt for image generation
        - image (ImageArtifact): Single input image (required for seededit-3.0-i2i, hidden for other models)
        - images (list): Multiple input images (seedream-4.5 supports up to 14, seedream-4.0 up to 10)
        - size (str): Image size specification (dynamic options based on selected model)
        - seed (int): Random seed for reproducible results
        - guidance_scale (float): Guidance scale (hidden for v4, visible for v3 models)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_url (ImageUrlArtifact): Generated image as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Seedream models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="seedream-4.5",
                tooltip="Select the Seedream model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["seedream-4.5", "seedream-4.0", "seedream-3.0-t2i", "seededit-3.0-i2i"])},
            )
        )

        # Core parameters
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for image generation (max 600 words recommended)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the image you want to generate...",
                    "display_name": "Prompt",
                },
            )
        )

        # Optional single image input for seededit-3.0-i2i (backwards compatibility)
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Input image (required for seededit-3.0-i2i)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Multiple image inputs for seedream-4.5/4.0 (up to 14/10 images)
        self.add_parameter(
            ParameterList(
                name="images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                ],
                default_value=[],
                tooltip="Input images for seedream (up to 14 for v4.5, 10 for v4.0)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "Input Images"},
            )
        )

        # Size parameter - will be updated dynamically based on model selection
        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="2K",
                tooltip="Image size specification",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SIZE_OPTIONS["seedream-4.5"])},
            )
        )

        # Seed parameter
        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                default_value=-1,
                tooltip="Random seed for reproducible results (-1 for random)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Guidance scale for seedream-3.0-t2i
        self.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                default_value=2.5,
                tooltip="Guidance scale (seedream-3.0-t2i only, default: 2.5)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide": True},
            )
        )

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
                name="image_url",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="Generated image as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

        # Initialize parameter visibility based on default model (seedream-4.5)
        self._initialize_parameter_visibility()

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model") or "seedream-4.5"
        if default_model in ("seedream-4.5", "seedream-4.0"):
            # Hide single image input, show images list, hide guidance scale
            self.hide_parameter_by_name("image")
            self.show_parameter_by_name("images")
            self.hide_parameter_by_name("guidance_scale")
        elif default_model == "seedream-3.0-t2i":
            # Hide image inputs (not supported), show guidance scale
            self.hide_parameter_by_name("image")
            self.hide_parameter_by_name("images")
            self.show_parameter_by_name("guidance_scale")
        elif default_model == "seededit-3.0-i2i":
            # Show single image input (required), hide images list, show guidance scale
            self.show_parameter_by_name("image")
            self.hide_parameter_by_name("images")
            self.show_parameter_by_name("guidance_scale")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options and parameter visibility based on model selection."""
        if parameter.name == "model" and value in SIZE_OPTIONS:
            self._update_model_parameters(value)
        return super().after_value_set(parameter, value)

    def _update_model_parameters(self, model: str) -> None:
        """Update parameters and UI based on selected model."""
        new_choices = SIZE_OPTIONS[model]
        current_size = self.get_parameter_value("size")

        if model in ("seedream-4.5", "seedream-4.0"):
            self._configure_v4_models(model, new_choices, current_size)
        elif model == "seedream-3.0-t2i":
            self._configure_v3_t2i_model(new_choices, current_size)
        elif model == "seededit-3.0-i2i":
            self._configure_seededit_model(new_choices, current_size)

    def _configure_v4_models(self, model: str, new_choices: list[str], current_size: str) -> None:
        """Configure UI for seedream-4.5 and seedream-4.0 models."""
        self.hide_parameter_by_name("image")
        self.show_parameter_by_name("images")
        self.hide_parameter_by_name("guidance_scale")

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            default_size = "2K" if model == "seedream-4.5" else "1K"
            default_size = default_size if default_size in new_choices else new_choices[0]
            self._update_option_choices("size", new_choices, default_size)

    def _configure_v3_t2i_model(self, new_choices: list[str], current_size: str) -> None:
        """Configure UI for seedream-3.0-t2i model."""
        self.hide_parameter_by_name("image")
        self.hide_parameter_by_name("images")
        self.show_parameter_by_name("guidance_scale")
        self.set_parameter_value("guidance_scale", 2.5)

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            self._update_option_choices("size", new_choices, "2048x2048")

    def _configure_seededit_model(self, new_choices: list[str], current_size: str) -> None:
        """Configure UI for seededit-3.0-i2i model."""
        self.show_parameter_by_name("image")
        self.hide_parameter_by_name("images")
        self.show_parameter_by_name("guidance_scale")

        image_param = self.get_parameter_by_name("image")
        if image_param:
            image_param.tooltip = "Input image (required for seededit-3.0-i2i)"
            image_param.ui_options["display_name"] = "Input Image"

        self.set_parameter_value("guidance_scale", 2.5)

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            self._update_option_choices("size", new_choices, "adaptive")

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before running the node."""
        exceptions = []
        model = self.get_parameter_value("model")

        # Validate image count for models that support multiple images
        if model in MAX_IMAGES_PER_MODEL:
            max_images = MAX_IMAGES_PER_MODEL[model]
            images = self.get_parameter_list_value("images") or []
            if len(images) > max_images:
                exceptions.append(
                    ValueError(f"{self.name}: {model} supports maximum {max_images} images, got {len(images)}")
                )

        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        params = self._get_parameters()

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        model = params["model"]
        self._log(f"Generating image with {model}")

        # Submit request to get generation ID
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
            # HTTP error during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        params = {
            "model": self.get_parameter_value("model") or "seedream-4.5",
            "prompt": self.get_parameter_value("prompt") or "",
            "image": self.get_parameter_value("image"),
            "size": self.get_parameter_value("size") or "2K",
            "seed": self.get_parameter_value("seed") or -1,
            "guidance_scale": self.get_parameter_value("guidance_scale") or 2.5,
            "watermark": False,
        }

        # Get image list for seedream-4.5 and seedream-4.0
        if params["model"] in ("seedream-4.5", "seedream-4.0"):
            params["images"] = self.get_parameter_list_value("images") or []

        return params

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str | None:
        payload = await self._build_payload(params)
        # Map friendly model name to API model ID
        api_model_id = MODEL_MAPPING.get(params["model"], params["model"])
        proxy_url = urljoin(self._proxy_base, f"models/{api_model_id}")

        self._log(f"Submitting request to Griptape model proxy with model: {params['model']}")
        self._log_request(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(proxy_url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                response_json = response.json()
                self._log("Request submitted successfully")
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            # Try to parse error response body
            try:
                error_json = e.response.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        # Extract generation_id from response
        generation_id = response_json.get("generation_id")
        if generation_id:
            self.parameter_output_values["generation_id"] = str(generation_id)
            self._log(f"Submitted. generation_id={generation_id}")
            return str(generation_id)
        self._log("No generation_id returned from POST response")
        return None

    async def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        model = params["model"]
        # Map friendly model name to API model ID
        api_model_id = MODEL_MAPPING.get(model, model)
        payload = {
            "model": api_model_id,
            "prompt": params["prompt"],
            "size": params["size"],
            "response_format": "url",
            "watermark": params["watermark"],
        }

        # Add seed if not -1
        if params["seed"] != -1:
            payload["seed"] = params["seed"]

        # Model-specific parameters
        if model in ("seedream-4.5", "seedream-4.0"):
            # Add multiple images if provided for v4.5/v4.0
            images = params.get("images", [])
            if images:
                image_array = []
                for img in images:
                    image_data = await self._process_input_image(img)
                    if image_data:
                        image_array.append(image_data)
                if image_array:
                    payload["image"] = image_array

        elif model == "seedream-3.0-t2i":
            # Add guidance scale for v3 t2i
            payload["guidance_scale"] = params["guidance_scale"]

        elif model == "seededit-3.0-i2i":
            # Add guidance scale and required image for seededit
            payload["guidance_scale"] = params["guidance_scale"]
            image_data = await self._process_input_image(params["image"])
            if image_data:
                payload["image"] = image_data

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
            self._log(f"Failed to extract image value: {e}")

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
            self._log(f"Failed to download image from URL {url}: {e}")
        return None

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = deepcopy(payload)
            # Truncate long prompts
            prompt = sanitized_payload.get("prompt", "")
            if len(prompt) > PROMPT_TRUNCATE_LENGTH:
                sanitized_payload["prompt"] = prompt[:PROMPT_TRUNCATE_LENGTH] + "..."
            # Redact base64 image data
            if "image" in sanitized_payload:
                image_data = sanitized_payload["image"]
                if isinstance(image_data, list):
                    # Handle array of images
                    redacted_images = []
                    for img in image_data:
                        if isinstance(img, str) and img.startswith("data:image/"):
                            parts = img.split(",", 1)
                            header = parts[0] if parts else "data:image/"
                            b64_len = len(parts[1]) if len(parts) > 1 else 0
                            redacted_images.append(f"{header},<base64 data length={b64_len}>")
                        else:
                            redacted_images.append(img)
                    sanitized_payload["image"] = redacted_images
                elif isinstance(image_data, str) and image_data.startswith("data:image/"):
                    # Handle single image
                    parts = image_data.split(",", 1)
                    header = parts[0] if parts else "data:image/"
                    b64_len = len(parts[1]) if len(parts) > 1 else 0
                    sanitized_payload["image"] = f"{header},<base64 data length={b64_len}>"

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        """Poll the generations endpoint until ready."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = 240  # 20 minutes with 5s intervals
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    result_json = response.json()

                    # Update provider_response with latest polling data
                    self.parameter_output_values["provider_response"] = result_json

                    status = result_json.get("status", "unknown")
                    self._log(f"Status: {status}")

                    if status == "COMPLETED":
                        # Fetch the actual result
                        await self._fetch_result(generation_id, headers, client)
                        return
                    if status in ["FAILED", "ERROR"]:
                        self._log(f"Generation failed with status: {status}")
                        self._set_safe_defaults()
                        # Extract error details from the response
                        error_details = self._extract_error_details(result_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

                    # Still processing (QUEUED or RUNNING), wait before next poll
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(poll_interval)

                except httpx.HTTPStatusError as e:
                    self._log(f"HTTP error while polling: {e.response.status_code} - {e.response.text}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: HTTP {e.response.status_code}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return
                except Exception as e:
                    self._log(f"Error while polling: {e}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: {e}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return

            # Timeout reached
            self._log("Polling timed out waiting for result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Image generation timed out after {max_attempts * poll_interval} seconds waiting for result.",
            )

    async def _fetch_result(self, generation_id: str, headers: dict[str, str], client: httpx.AsyncClient) -> None:
        """Fetch the final result from the generations endpoint."""
        result_url = urljoin(self._proxy_base, f"generations/{generation_id}/result")
        self._log(f"Fetching result from {result_url}")

        try:
            response = await client.get(result_url, headers=headers, timeout=60)
            response.raise_for_status()
            result_json = response.json()

            # Update provider_response with the final result
            self.parameter_output_values["provider_response"] = result_json

            # Extract image data (expecting single image)
            data = result_json.get("data", [])
            if not data:
                self._log("No image data in result")
                self.parameter_output_values["image_url"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="Generation completed but no image data was found in the response.",
                )
                return

            # Take first image from response
            image_data = data[0]

            # Always using URL format
            image_url = image_data.get("url")
            if image_url:
                await self._save_image_from_url(image_url, generation_id)
            else:
                self._log("No image URL in result")
                self.parameter_output_values["image_url"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="Generation completed but no image URL was found in the response.",
                )
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error fetching result: {e.response.status_code} - {e.response.text}")
            self._set_safe_defaults()
            error_msg = f"Failed to fetch generation result: HTTP {e.response.status_code}"
            self._set_status_results(was_successful=False, result_details=error_msg)
        except Exception as e:
            self._log(f"Error fetching result: {e}")
            self._set_safe_defaults()
            error_msg = f"Failed to fetch generation result: {e}"
            self._set_status_results(was_successful=False, result_details=error_msg)

    async def _save_image_from_url(self, image_url: str, generation_id: str | None = None) -> None:
        """Download and save the image from the provided URL."""
        try:
            self._log("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = (
                    f"seedream_image_{generation_id}.jpg" if generation_id else f"seedream_image_{int(time.time())}.jpg"
                )
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved image to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Image generated successfully and saved as {filename}."
                )
            else:
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
                self._set_status_results(
                    was_successful=True,
                    result_details="Image generated successfully. Using provider URL (could not download image bytes).",
                )
        except Exception as e:
            self._log(f"Failed to save image from URL: {e}")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image generated successfully. Using provider URL (could not save to static storage: {e}).",
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

        # Check for v2 API status_detail first (for FAILED/ERROR statuses)
        status_detail = response_json.get("status_detail")
        if status_detail:
            error_msg = self._format_status_detail_error(status_detail)
            if error_msg:
                return error_msg

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
        return f"Generation failed.\n\nFull API response:\n{response_json}"

    def _format_status_detail_error(self, status_detail: dict[str, Any]) -> str | None:
        r"""Format error message from v2 API status_detail field.

        Args:
            status_detail: The status_detail object from a FAILED/ERROR generation response
            Example: {"error": "invalid input", "details": "{\"error\":{\"code\":\"...\",\"message\":\"...\"}}"}

        Returns:
            A formatted error message string, or None if status_detail doesn't contain useful error info
        """
        if not isinstance(status_detail, dict):
            return None

        self._log(f"Parsing status_detail: {status_detail}")

        # Extract top-level error message
        top_error = status_detail.get("error", "")

        # Try to parse the details field (which is a JSON string)
        details_str = status_detail.get("details")
        if details_str and isinstance(details_str, str):
            self._log(f"Found details string, attempting to parse: {details_str[:200]}...")
            try:
                details_obj = _json.loads(details_str)
                self._log(f"Parsed details object: {details_obj}")

                if isinstance(details_obj, dict):
                    error_info = details_obj.get("error", {})
                    if isinstance(error_info, dict):
                        error_code = error_info.get("code", "")
                        error_message = error_info.get("message", "")

                        self._log(f"Extracted error_code={error_code}, error_message length={len(error_message)}")

                        if error_message:
                            # Use the detailed error message as the primary message
                            formatted_msg = error_message
                            if error_code:
                                formatted_msg += f"\nError Code: {error_code}"
                            return formatted_msg
            except Exception as e:
                # If we can't parse details, fall through to simpler format
                self._log(f"Failed to parse status_detail.details JSON: {e}")
        else:
            self._log(f"No details string found or details is not a string: {type(details_str)}")

        # If we have a top-level error but couldn't parse details
        if top_error:
            return f"Generation failed: {top_error}"

        return None

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
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image_url"] = None

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
