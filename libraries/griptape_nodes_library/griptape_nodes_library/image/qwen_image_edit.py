from __future__ import annotations

import json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from http import HTTPStatus
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["QwenImageEdit"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model options
MODEL_OPTIONS = [
    "qwen-image-edit",
    "qwen-image-edit-plus",
    "qwen-image-edit-plus-2025-10-30",
]

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"
STATUS_REQUEST_MODERATED = "Request Moderated"
STATUS_CONTENT_MODERATED = "Content Moderated"

# Maximum number of images for editing
MAX_IMAGES = 6


class QwenImageEdit(SuccessFailureNode):
    """Edit images using Qwen image editing models via Griptape model proxy.

    Supports editing 1-6 input images with text instructions.

    Documentation: https://www.alibabacloud.com/help/en/model-studio/qwen-image-edit-api

    Inputs:
        - model (str): Qwen edit model to use (default: "qwen-image-edit-plus")
            qwen-image-edit: Generates only 1 image
            qwen-image-edit-plus: Generates 1-6 images
            qwen-image-edit-plus-2025-10-30: Generates 1-6 images
        - editing_instruction (str): Text instruction describing the desired edits (max 800 characters)
            When editing multiple images, use "Image 1", "Image 2", "Image 3" to refer to specific images
        - images (list): List of 1-6 input images to edit (required)
            Supports JPG, JPEG, PNG, BMP, TIFF, WEBP
            Resolution: 384-3072 pixels (width and height)
            Size: Max 10 MB per image
            Note: The number of output images generated equals the number of input images (1-6)
        - negative_prompt (str): Description of content to avoid (max 500 characters)
        - watermark (bool): Add "Qwen-Image" watermark to bottom-right corner (default: False)
        - randomize_seed (bool): If true, randomize the seed on each run
        - seed (int): Random seed for reproducible results (default: 42)

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
        self.description = "Edit images using Qwen image editing models via Griptape model proxy"

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
                default_value="qwen-image-edit-plus",
                tooltip="Select the Qwen image editing model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Editing instruction parameter
        self.add_parameter(
            Parameter(
                name="editing_instruction",
                input_types=["str"],
                type="str",
                tooltip="Editing instruction (max 800 characters). Use 'Image 1', 'Image 2', 'Image 3' to refer to specific images.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the edits you want to make to the image(s)...",
                    "display_name": "Editing Instruction",
                },
            )
        )

        # Images list for editing (1-6 images)
        self.add_parameter(
            ParameterList(
                name="images",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                default_value=[],
                tooltip="List of 1-6 images to edit (JPG, PNG, BMP, TIFF, WEBP; 384-3072px; max 10MB each)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={
                    "display_name": "Images to Edit",
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
                    "placeholder_text": "Describe what you don't want in the image...",
                    "display_name": "Negative Prompt",
                },
            )
        )

        # Watermark parameter
        self.add_parameter(
            Parameter(
                name="watermark",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Add 'Qwen-Image' watermark in bottom-right corner",
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
            result_details_tooltip="Details about the image editing result or any errors",
            result_details_placeholder="Editing status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

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
        logger.info("Editing images with %s", model)

        # Submit request and get synchronous response
        try:
            response = await self._submit_request(params, headers)
            if not response:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No response returned from API. Cannot proceed with editing.",
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
        images = self.get_parameter_value("images")

        # Validate images
        if not images or len(images) == 0:
            msg = "At least 1 image is required for editing"
            raise ValueError(msg)
        if model == "qwen-image-edit" and len(images) != 1:
            msg = f"qwen-image-edit only supports 1 image for editing (got {len(images)} images)"
            raise ValueError(msg)
        if len(images) > MAX_IMAGES:
            msg = f"Maximum {MAX_IMAGES} images allowed for editing (got {len(images)})"
            raise ValueError(msg)

        # Automatically set num_images to match the number of input images
        num_images = len(images)

        # Validate num_images based on model
        if model == "qwen-image-edit" and num_images != 1:
            msg = f"qwen-image-edit only supports 1 image for editing (got {num_images} images)"
            raise ValueError(msg)

        return {
            "model": model,
            "editing_instruction": self.get_parameter_value("editing_instruction") or "",
            "images": images,
            "num_images": num_images,
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "watermark": self.get_parameter_value("watermark") or False,
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
        payload = await self._build_payload(params)
        proxy_url = urljoin(self._proxy_base, f"models/{params['model']}")

        logger.info("Submitting request to Griptape model proxy with %s", params["model"])
        self._log_request(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(proxy_url, json=payload, headers=headers, timeout=60)
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
        # Build content array with images first, then text instruction
        content = []

        # Process images (1-6 images)
        images_list = params["images"] if isinstance(params["images"], list) else []
        for image_input in images_list:
            image_data = await self._process_input_image(image_input)
            if image_data:
                content.append({"image": image_data})

        # Add editing instruction as text
        content.append({"text": params["editing_instruction"]})

        # Flatten structure - parameters should be at top level for MultiModalConversation.call()
        payload = {
            "model": params["model"],
            "messages": [{"role": "user", "content": content}],
            "n": params["num_images"],
            "watermark": params["watermark"],
            "seed": params["seed"],
        }

        # Add negative prompt if provided
        if params["negative_prompt"]:
            payload["negative_prompt"] = params["negative_prompt"]

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

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = deepcopy(payload)
            # Truncate long editing instructions
            if "messages" in sanitized_payload:
                for msg in sanitized_payload["messages"]:
                    if "content" in msg:
                        for item in msg["content"]:
                            if "text" in item:
                                text = item["text"]
                                if len(text) > PROMPT_TRUNCATE_LENGTH:
                                    item["text"] = text[:PROMPT_TRUNCATE_LENGTH] + "..."
                            # Redact base64 image data
                            if "image" in item:
                                image_data = item["image"]
                                if isinstance(image_data, str) and image_data.startswith("data:image/"):
                                    parts = image_data.split(",", 1)
                                    header = parts[0] if parts else "data:image/"
                                    b64_len = len(parts[1]) if len(parts) > 1 else 0
                                    item["image"] = f"{header},<base64 data length={b64_len}>"

            logger.info("Request payload: %s", json.dumps(sanitized_payload, indent=2))

    async def _handle_response(self, response: dict[str, Any]) -> None:
        """Handle Qwen synchronous response and extract image.

        Response shape:
        {
            "status_code": 200,
            "request_id": "...",
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"image": "https://..."},
                                {"image": "https://..."}
                            ]
                        }
                    }
                ]
            }
        }
        """
        self.parameter_output_values["provider_response"] = response

        # Extract request_id for generation_id
        request_id = response.get("request_id", response.get("id", ""))
        self.parameter_output_values["generation_id"] = str(request_id)

        # Check status_code
        status_code = response.get("status_code")
        if status_code and status_code != HTTPStatus.OK:
            logger.error("Editing failed with status_code: %s", status_code)
            self._set_safe_defaults()
            error_details = self._extract_error_details(response)
            self._set_status_results(was_successful=False, result_details=error_details)
            return

        try:
            choices = response.get("choices", [])
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", [])
            first_content_item = content[0]
            image_url = first_content_item.get("image")
        except Exception as e:
            logger.error("Failed to extract image URL from response: %s", e)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Editing completed but failed to extract image URL from the response.",
            )
            return

        if image_url:
            await self._save_image_from_url(image_url)
        else:
            logger.warning("No image URL found in content")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Editing completed but no image URL was found in the response.",
            )

    async def _save_image_from_url(self, image_url: str) -> None:
        """Download and save the image from the provided URL."""
        try:
            logger.info("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"qwen_edit_{int(time.time())}.jpg"
                from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=saved_url, name=filename)
                logger.info("Saved image to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Image edited successfully and saved as {filename}."
                )
            else:
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
                self._set_status_results(
                    was_successful=True,
                    result_details="Image edited successfully. Using provider URL (could not download image bytes).",
                )
        except Exception as e:
            logger.error("Failed to save image from URL: %s", e)
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image edited successfully. Using provider URL (could not save to static storage: {e}).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response.

        Args:
            response_json: The JSON response from the API that may contain error information

        Returns:
            A formatted error message string
        """
        if not response_json:
            return "Editing failed with no error details provided by API."

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
        return f"Editing failed.\n\nFull API response:\n{response_json}"

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
            return f"Editing failed: {result['error']}"
        return f"Editing failed with status '{status}'."

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
        return f"Editing failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"Editing failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"Editing failed with error: {top_level_error!s}"

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
