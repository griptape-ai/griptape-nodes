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
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["TopazImageTransform"]

# Output format options
OUTPUT_FORMAT_OPTIONS = ["jpeg", "png", "webp"]

# Generative enhance models
GENERATIVE_MODELS = ["Redefine", "Recovery", "Recovery V2"]

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"


class TopazImageTransform(SuccessFailureNode):
    """Transform images using Topaz Labs generative models via Griptape model proxy.

    This node provides AI-powered image transformation using generative models that can
    significantly transform and improve images beyond what standard enhancement provides.

    Inputs:
        - model (str): Generative model to use ("Redefine", "Recovery", or "Recovery V2")
        - image_input (ImageArtifact/ImageUrlArtifact): Input image to process
        - prompt (str): [Redefine only] Description of the resulting image (max 1024 chars)
        - autoprompt (bool): [Redefine only] Use auto-prompting model to generate a prompt
        - creativity (int): [Redefine only] Lower values maintain fidelity, higher values more creative (1-6)
        - texture (int): [Redefine only] Add texture to the image (1-5)
        - sharpen (float): [Redefine only] Slightly sharpens the image (0.0-1.0)
        - denoise (float): [Redefine only] Reduces noise in the image (0.0-1.0)
        - detail (float): [Recovery only] Adjusts level of added detail after rendering (0.0-1.0)
        - seed (int): Random seed for reproducible results
        - output_format (str): Desired format of the output image

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_output (ImageUrlArtifact): Processed image as URL artifact
        - was_successful (bool): Whether the processing succeeded
        - result_details (str): Details about the processing result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Transform images using Topaz Labs generative models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Model selection
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Redefine",
                tooltip="Generative enhancement model: Redefine for creative changes, Recovery for restoring details",
                allow_output=False,
                traits={Options(choices=GENERATIVE_MODELS)},
            )
        )

        # Input image
        self.add_parameter(
            Parameter(
                name="image_input",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="Input image to process",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Prompt parameter (Redefine only)
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="A description of the resulting image (max 1024 characters). Use descriptive statements rather than directives.",
                multiline=True,
                placeholder_text="e.g., girl with red hair and blue eyes",
                allow_output=False,
            )
        )

        # Auto-prompt parameter (Redefine only)
        self.add_parameter(
            Parameter(
                name="autoprompt",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Use auto-prompting model to generate a prompt. If enabled, ignores manual prompt input.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Auto Prompt"},
            )
        )

        # Creativity parameter (Redefine only)
        self.add_parameter(
            ParameterInt(
                name="creativity",
                default_value=3,
                tooltip="Lower values maintain highest fidelity. Higher values provide more creative results (1-6).",
                allow_output=False,
                slider=True,
                min_val=1,
                max_val=6,
            )
        )

        # Texture parameter (Redefine only)
        self.add_parameter(
            ParameterInt(
                name="texture",
                default_value=1,
                tooltip="Add texture to the image. Recommend 1 for low creativity, 3 for higher creativity (1-5).",
                allow_output=False,
                slider=True,
                min_val=1,
                max_val=5,
            )
        )

        # Sharpen parameter (Redefine only)
        self.add_parameter(
            ParameterFloat(
                name="sharpen",
                default_value=0.0,
                tooltip="Slightly sharpens the image (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Denoise parameter (Redefine only)
        self.add_parameter(
            ParameterFloat(
                name="denoise",
                default_value=0.0,
                tooltip="Reduces noise in the image (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Detail parameter (Recovery models only)
        self.add_parameter(
            ParameterFloat(
                name="detail",
                default_value=0.5,
                tooltip="Adjusts the level of added detail after rendering (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
                hide=True,
            )
        )

        # Seed parameter
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

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

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allow_input=False,
                allow_property=False,
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
                name="image_output",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="Processed image as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the image processing result or any errors",
            result_details_placeholder="Processing status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        self._seed_parameter.after_value_set(parameter, value)

        if parameter.name == "model":
            if value == "Redefine":
                # Show Redefine-specific params
                self.show_parameter_by_name("prompt")
                self.show_parameter_by_name("autoprompt")
                self.show_parameter_by_name("creativity")
                self.show_parameter_by_name("texture")
                self.show_parameter_by_name("sharpen")
                self.show_parameter_by_name("denoise")
                # Hide Recovery-specific params
                self.hide_parameter_by_name("detail")
            elif value in ["Recovery", "Recovery V2"]:
                # Hide Redefine-specific params
                self.hide_parameter_by_name("prompt")
                self.hide_parameter_by_name("autoprompt")
                self.hide_parameter_by_name("creativity")
                self.hide_parameter_by_name("texture")
                self.hide_parameter_by_name("sharpen")
                self.hide_parameter_by_name("denoise")
                # Show Recovery-specific params
                self.show_parameter_by_name("detail")

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        self.preprocess()
        self._clear_execution_status()

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
        self._log(f"Processing image with Topaz image transform using {model}")

        # Submit request to get generation ID
        try:
            generation_id = await self._submit_request(params, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with processing.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        model = self.get_parameter_value("model") or "Redefine"
        params = {
            "model": model,
            "image_input": self.get_parameter_value("image_input"),
            "seed": self._seed_parameter.get_seed(),
            "output_format": self.get_parameter_value("output_format") or "jpeg",
        }

        if model == "Redefine":
            params.update({
                "prompt": self.get_parameter_value("prompt") or "",
                "autoprompt": self.get_parameter_value("autoprompt") or False,
                "creativity": self.get_parameter_value("creativity") or 3,
                "texture": self.get_parameter_value("texture") or 1,
                "sharpen": self.get_parameter_value("sharpen") or 0.0,
                "denoise": self.get_parameter_value("denoise") or 0.0,
            })
        elif model in ["Recovery", "Recovery V2"]:
            params.update({
                "detail": self.get_parameter_value("detail") or 0.5,
            })

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
        proxy_url = urljoin(self._proxy_base, "models/topaz-enhance-gen")

        self._log("Submitting request to Griptape model proxy for topaz-enhance-gen")
        self._log_request(payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(proxy_url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                response_json = response.json()
                self._log("Request submitted successfully")
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
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
        payload = {
            "model": params["model"],
            "output_format": params["output_format"],
        }

        model = params["model"]

        if model == "Redefine":
            autoprompt = params.get("autoprompt", False)
            prompt = params.get("prompt", "")

            # Only include prompt if autoprompt is disabled and prompt is provided
            if not autoprompt and prompt and prompt.strip():
                payload["prompt"] = prompt.strip()

            payload["autoprompt"] = autoprompt
            payload["creativity"] = int(params.get("creativity", 3))
            payload["texture"] = int(params.get("texture", 1))
            payload["sharpen"] = float(params.get("sharpen", 0.0))
            payload["denoise"] = float(params.get("denoise", 0.0))

        elif model in ["Recovery", "Recovery V2"]:
            payload["detail"] = float(params.get("detail", 0.5))

        # Add seed if provided
        if params.get("seed") is not None:
            payload["seed"] = params["seed"]

        # Add input image
        image_input = params.get("image_input")
        if image_input:
            input_image_data = await self._process_input_image(image_input)
            if input_image_data:
                payload["image"] = input_image_data

        return payload

    async def _process_input_image(self, image_input: Any) -> str | None:
        """Process input image and convert to base64 data URI."""
        if not image_input:
            return None

        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        return await self._convert_to_base64_data_uri(image_value)

    def _extract_image_value(self, image_input: Any) -> str | None:
        """Extract string value from various image input types."""
        if isinstance(image_input, str):
            return image_input

        try:
            if hasattr(image_input, "value"):
                value = getattr(image_input, "value", None)
                if isinstance(value, str):
                    return value

            if hasattr(image_input, "base64"):
                b64 = getattr(image_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception as e:
            self._log(f"Failed to extract image value: {e}")

        return None

    async def _convert_to_base64_data_uri(self, image_value: str) -> str | None:
        """Convert image value to base64 data URI."""
        if image_value.startswith("data:image/"):
            return image_value

        if image_value.startswith(("http://", "https://")):
            return await self._download_and_encode_image(image_value)

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
            if "image" in sanitized_payload:
                image_data = sanitized_payload["image"]
                if isinstance(image_data, str) and image_data.startswith("data:image/"):
                    parts = image_data.split(",", 1)
                    header = parts[0] if parts else "data:image/"
                    b64_len = len(parts[1]) if len(parts) > 1 else 0
                    sanitized_payload["image"] = f"{header},<base64 data length={b64_len}>"

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        """Poll the generations endpoint until ready."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = 180  # 15 minutes with 5s intervals (generative models take longer)
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    result_json = response.json()

                    self.parameter_output_values["provider_response"] = result_json

                    status = result_json.get("status", "unknown")
                    self._log(f"Status: {status}")

                    if status == "Ready":
                        sample_url = result_json.get("result", {}).get("sample")
                        if sample_url:
                            await self._handle_success(result_json, sample_url)
                        else:
                            self._log("No sample URL found in ready result")
                            self._set_safe_defaults()
                            self._set_status_results(
                                was_successful=False,
                                result_details="Processing completed but no image URL was found in the response.",
                            )
                        return
                    if status in [STATUS_FAILED, STATUS_ERROR]:
                        self._log(f"Processing failed with status: {status}")
                        self._set_safe_defaults()
                        error_details = self._extract_error_details(result_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

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

            self._log("Polling timed out waiting for result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Image transformation timed out after {max_attempts * poll_interval} seconds waiting for result.",
            )

    async def _handle_success(self, response: dict[str, Any], image_url: str) -> None:
        """Handle successful processing result."""
        self.parameter_output_values["provider_response"] = response
        await self._save_image_from_url(image_url)

    async def _save_image_from_url(self, image_url: str) -> None:
        """Download and save the image from the provided URL."""
        try:
            self._log("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"topaz_transform_{int(time.time())}.jpg"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image_output"] = ImageUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved image to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Image transformed successfully and saved as {filename}."
                )
            else:
                self.parameter_output_values["image_output"] = ImageUrlArtifact(value=image_url)
                self._set_status_results(
                    was_successful=True,
                    result_details="Image transformed successfully. Using provider URL (could not download image bytes).",
                )
        except Exception as e:
            self._log(f"Failed to save image from URL: {e}")
            self.parameter_output_values["image_output"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image transformed successfully. Using provider URL (could not save to static storage: {e}).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Processing failed with no error details provided by API."

        top_level_error = response_json.get("error")

        if top_level_error:
            if isinstance(top_level_error, dict):
                error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
                return f"Processing failed with error: {error_msg}"
            return f"Processing failed with error: {top_level_error!s}"

        status = response_json.get("status")
        if status in [STATUS_FAILED, STATUS_ERROR]:
            result = response_json.get("result", {})
            if isinstance(result, dict) and result.get("error"):
                return f"Processing failed: {result['error']}"
            return f"Processing failed with status '{status}'."

        return f"Processing failed.\n\nFull API response:\n{response_json}"

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image_output"] = None

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
