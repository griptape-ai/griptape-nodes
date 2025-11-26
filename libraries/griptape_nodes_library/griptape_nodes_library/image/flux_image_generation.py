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

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.api_key_provider_parameter import (
    ApiKeyProviderParameter,
    ApiKeyValidationResult,
)
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["FluxImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# API timeout in seconds
API_TIMEOUT = 60

# Aspect ratio options
ASPECT_RATIO_OPTIONS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21", "3:7", "7:3"]

# Output format options
OUTPUT_FORMAT_OPTIONS = ["jpeg", "png"]

# Model options
MODEL_OPTIONS = ["flux-kontext-pro"]

# Safety tolerance options
SAFETY_TOLERANCE_OPTIONS = ["least restrictive", "moderate", "most restrictive"]

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"
STATUS_REQUEST_MODERATED = "Request Moderated"
STATUS_CONTENT_MODERATED = "Content Moderated"

# API Configuration for proxy API
PROXY_URL_TEMPLATE = "{base}models/{model}"
POLLING_URL_TEMPLATE = "{base}generations/{id}"
RESPONSE_ID_KEY = "generation_id"


class FluxImageGeneration(SuccessFailureNode):
    """Generate images using Flux models via API (supports user-provided API keys via proxy).

    Inputs:
        - model (str): Flux model to use (default: "flux-kontext-pro")
        - prompt (str): Text description of the desired image
        - input_image (ImageArtifact): Optional input image for image-to-image generation
        - aspect_ratio (str): Desired aspect ratio (e.g., "16:9", default: "1:1")
        - seed (int): Random seed for reproducible results (-1 for random)
        - prompt_upsampling (bool): If true, performs upsampling on the prompt
        - output_format (str): Desired format of the output image ("jpeg" or "png")
        - safety_tolerance (str): Content moderation preset ("least restrictive", "moderate", or "most restrictive")

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_url (ImageUrlArtifact): Generated image as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    USER_API_KEY_NAME = "BFL_API_KEY"
    USER_API_KEY_URL = "https://dashboard.bfl.ai/api/keys"
    USER_API_KEY_PROVIDER_NAME = "BlackForest Labs"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Flux models via API (supports user-provided API keys via proxy)"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Add API key provider component
        self._api_key_provider = ApiKeyProviderParameter(
            node=self,
            api_key_name=self.USER_API_KEY_NAME,
            provider_name=self.USER_API_KEY_PROVIDER_NAME,
            api_key_url=self.USER_API_KEY_URL,
        )
        self._api_key_provider.add_parameters()
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="flux-kontext-pro",
                tooltip="Select the Flux model to use",
                allow_output=False,
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Core parameters
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text description of the desired image",
                multiline=True,
                placeholder_text="Describe the image you want to generate...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )

        # Optional input image for image-to-image generation
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional input image for image-to-image generation (supports up to 20MB or 20 megapixels)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Aspect ratio parameter
        self.add_parameter(
            ParameterString(
                name="aspect_ratio",
                default_value="1:1",
                tooltip="Desired aspect ratio (e.g., '16:9'). All outputs are ~1MP total.",
                allow_output=False,
                traits={Options(choices=ASPECT_RATIO_OPTIONS)},
            )
        )

        # Seed parameter
        self.add_parameter(
            ParameterInt(
                name="seed",
                default_value=-1,
                tooltip="Random seed for reproducible results (-1 for random)",
                allow_output=False,
            )
        )

        # Prompt upsampling parameter
        self.add_parameter(
            ParameterBool(
                name="prompt_upsampling",
                default_value=False,
                tooltip="If true, performs upsampling on the prompt",
                allow_output=False,
            )
        )

        # Output format parameter
        self.add_parameter(
            ParameterString(
                name="output_format",
                default_value="jpeg",
                tooltip="Desired format of the output image",
                allow_output=False,
                traits={Options(choices=OUTPUT_FORMAT_OPTIONS)},
            )
        )

        # Safety tolerance parameter
        self.add_parameter(
            ParameterString(
                name="safety_tolerance",
                default_value=SAFETY_TOLERANCE_OPTIONS[0],
                tooltip="Content moderation level",
                allow_output=False,
                traits={Options(choices=SAFETY_TOLERANCE_OPTIONS)},
            )
        )

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allow_input=False,
                allow_property=False,
                allow_output=True,
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from the API",
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

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        try:
            params = self._get_parameters()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        try:
            validation_result = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Build headers: always use proxy API key, optionally add user API key
        headers = {
            "Authorization": f"Bearer {validation_result.proxy_api_key}",
            "Content-Type": "application/json",
        }
        if validation_result.user_api_key:
            headers["X-GTC-PROXY-AUTH-API-KEY"] = validation_result.user_api_key

        model = params["model"]
        if validation_result.user_api_key:
            self._log(f"Generating image with {model} using Griptape model proxy with user-provided API key")
        else:
            self._log(f"Generating image with {model} using Griptape model proxy")

        # Submit request to get generation ID
        try:
            generation_id = await self._submit_request(params, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation ID returned from API. Cannot proceed with generation.",
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
        return {
            "model": self.get_parameter_value("model") or "flux-kontext-pro",
            "prompt": self.get_parameter_value("prompt") or "",
            "input_image": self.get_parameter_value("input_image"),
            "aspect_ratio": self.get_parameter_value("aspect_ratio") or "1:1",
            "seed": self.get_parameter_value("seed") or -1,
            "prompt_upsampling": self.get_parameter_value("prompt_upsampling") or False,
            "output_format": self.get_parameter_value("output_format") or "jpeg",
            "safety_tolerance": self._parse_safety_tolerance(self.get_parameter_value("safety_tolerance")),
        }

    def _parse_safety_tolerance(self, value: str | None) -> int:
        """Parse safety tolerance integer from preset string value.

        Args:
            value: One of "least restrictive", "moderate", or "most restrictive"

        Returns:
            Integer value: 6 for least restrictive, 3 for moderate, 0 for most restrictive

        Raises:
            ValueError: If value is None or not one of the expected options
        """
        if not value:
            msg = "safety_tolerance cannot be None or empty"
            raise ValueError(msg)

        if value == "most restrictive":
            return 0
        if value == "moderate":
            return 3
        if value == "least restrictive":
            return 6

        msg = f"Invalid safety_tolerance value: '{value}'. Must be one of: {SAFETY_TOLERANCE_OPTIONS}"
        raise ValueError(msg)

    def _validate_api_key(self) -> ApiKeyValidationResult:
        """Validate and return API key and whether to use user API.

        Returns:
            ApiKeyValidationResult: Named tuple containing api_key and use_user_api
        """
        return self._api_key_provider.validate_api_key()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._api_key_provider.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str | None:
        """Submit request to proxy API and return generation ID.

        Args:
            params: Request parameters
            headers: Request headers

        Returns:
            Generation ID string, or None if not found
        """
        payload = await self._build_payload(params)
        model = params["model"]
        url = PROXY_URL_TEMPLATE.format(base=self._proxy_base, model=model)

        self._log(f"Submitting request to Griptape model proxy with {model}")
        self._log_request(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=API_TIMEOUT)
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
        except httpx.ConnectTimeout as e:
            error_msg = (
                f"{self.name}: Connection to API timed out after {API_TIMEOUT} seconds. "
                f"This may indicate network connectivity issues or the API may be temporarily unavailable."
            )
            raise RuntimeError(error_msg) from e
        except httpx.TimeoutException as e:
            error_msg = (
                f"{self.name}: Request to API timed out after {API_TIMEOUT} seconds. "
                f"The API may be experiencing high load. Please try again later."
            )
            raise RuntimeError(error_msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        # Extract generation ID from response
        generation_id = response_json.get(RESPONSE_ID_KEY)

        if generation_id:
            self.parameter_output_values["generation_id"] = str(generation_id)
            self._log(f"Submitted. {RESPONSE_ID_KEY}={generation_id}")
            return str(generation_id)

        self._log(f"No {RESPONSE_ID_KEY} returned from POST response")
        return None

    async def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "prompt": params["prompt"],
            "aspect_ratio": params["aspect_ratio"],
            "prompt_upsampling": params["prompt_upsampling"],
            "output_format": params["output_format"],
            "safety_tolerance": params["safety_tolerance"],
        }

        # Add seed if not -1 (random)
        if params["seed"] != -1:
            payload["seed"] = params["seed"]

        # Add input image if provided
        input_image_data = await self._process_input_image(params["input_image"])
        if input_image_data:
            payload["input_image"] = input_image_data

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
            # Redact base64 input image data
            if "input_image" in sanitized_payload:
                image_data = sanitized_payload["input_image"]
                if isinstance(image_data, str) and image_data.startswith("data:image/"):
                    parts = image_data.split(",", 1)
                    header = parts[0] if parts else "data:image/"
                    b64_len = len(parts[1]) if len(parts) > 1 else 0
                    sanitized_payload["input_image"] = f"{header},<base64 data length={b64_len}>"

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        """Poll the proxy API endpoint until ready.

        Args:
            generation_id: The generation/request ID to poll for
            headers: Request headers
        """
        # Build polling URL for proxy API
        get_url = POLLING_URL_TEMPLATE.format(base=self._proxy_base, id=generation_id)

        max_attempts = 120  # 10 minutes with 5s intervals
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                    response = await client.get(get_url, headers=headers, timeout=API_TIMEOUT)
                    response.raise_for_status()
                    result_json = response.json()

                    # Update provider_response with latest polling data
                    self.parameter_output_values["provider_response"] = result_json

                    status = result_json.get("status", "unknown")
                    self._log(f"Status: {status}")

                    if status == "Ready":
                        # Extract the image URL from result.sample
                        sample_url = result_json.get("result", {}).get("sample")
                        if sample_url:
                            await self._handle_success(result_json, sample_url)
                        else:
                            self._log("No sample URL found in ready result")
                            self._set_safe_defaults()
                            self._set_status_results(
                                was_successful=False,
                                result_details="Generation completed but no image URL was found in the response.",
                            )
                        return
                    if status in [STATUS_FAILED, STATUS_ERROR, STATUS_REQUEST_MODERATED, STATUS_CONTENT_MODERATED]:
                        self._log(f"Generation failed with status: {status}")
                        self._set_safe_defaults()
                        # Extract error details from the response
                        error_details = self._extract_error_details(result_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

                    # Still processing, wait before next poll
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

    async def _handle_success(self, response: dict[str, Any], image_url: str) -> None:
        """Handle successful generation result."""
        self.parameter_output_values["provider_response"] = response
        await self._save_image_from_url(image_url)

    async def _save_image_from_url(self, image_url: str) -> None:
        """Download and save the image from the provided URL."""
        try:
            self._log("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"flux_image_{int(time.time())}.jpg"
                from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

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
        """Set safe default values for outputs."""
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
