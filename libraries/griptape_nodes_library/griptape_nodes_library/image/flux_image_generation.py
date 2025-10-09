from __future__ import annotations

import json as _json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger(__name__)

__all__ = ["FluxImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Aspect ratio options
ASPECT_RATIO_OPTIONS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21", "3:7", "7:3"]

# Output format options
OUTPUT_FORMAT_OPTIONS = ["jpeg", "png"]

# Model options
MODEL_OPTIONS = ["flux-kontext-pro"]


class FluxImageGeneration(DataNode):
    """Generate images using Flux models via Griptape model proxy.

    Inputs:
        - model (str): Flux model to use (default: "flux-kontext-pro")
        - prompt (str): Text description of the desired image
        - input_image (ImageArtifact): Optional input image for image-to-image generation
        - aspect_ratio (str): Desired aspect ratio (e.g., "16:9", default: "1:1")
        - seed (int): Random seed for reproducible results (-1 for random)
        - prompt_upsampling (bool): If true, performs upsampling on the prompt
        - output_format (str): Desired format of the output image ("jpeg" or "png")

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_url (ImageUrlArtifact): Generated image as URL artifact
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Flux models via Griptape model proxy"

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
                default_value="flux-kontext-pro",
                tooltip="Select the Flux model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Core parameters
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text description of the desired image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the image you want to generate...",
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
            Parameter(
                name="aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="1:1",
                tooltip="Desired aspect ratio (e.g., '16:9'). All outputs are ~1MP total.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=ASPECT_RATIO_OPTIONS)},
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

        # Prompt upsampling parameter
        self.add_parameter(
            Parameter(
                name="prompt_upsampling",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="If true, performs upsampling on the prompt",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Output format parameter
        self.add_parameter(
            Parameter(
                name="output_format",
                input_types=["str"],
                type="str",
                default_value="jpeg",
                tooltip="Desired format of the output image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=OUTPUT_FORMAT_OPTIONS)},
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

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        params = self._get_parameters()
        api_key = self._validate_api_key()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        model = params["model"]
        self._log(f"Generating image with {model}")

        # Submit request to get generation ID
        generation_id = self._submit_request(params, headers)
        if not generation_id:
            self._set_safe_defaults()
            return

        # Poll for result
        self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "model": self.get_parameter_value("model") or "flux-kontext-pro",
            "prompt": self.get_parameter_value("prompt") or "",
            "input_image": self.get_parameter_value("input_image"),
            "aspect_ratio": self.get_parameter_value("aspect_ratio") or "1:1",
            "seed": self.get_parameter_value("seed") or -1,
            "prompt_upsampling": self.get_parameter_value("prompt_upsampling") or False,
            "output_format": self.get_parameter_value("output_format") or "jpeg",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str | None:
        payload = self._build_payload(params)
        proxy_url = urljoin(self._proxy_base, f"models/{params['model']}")

        self._log(f"Submitting request to Griptape model proxy with {params['model']}")
        self._log_request(payload)

        try:
            response = requests.post(proxy_url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            response_json = response.json()
            self._log("Request submitted successfully")
        except requests.exceptions.HTTPError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            msg = f"{self.name} API error: {e.response.status_code}"
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

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "prompt": params["prompt"],
            "aspect_ratio": params["aspect_ratio"],
            "prompt_upsampling": params["prompt_upsampling"],
            "output_format": params["output_format"],
            "safety_tolerance": 6,  # Use default value as requested
        }

        # Add seed if not -1 (random)
        if params["seed"] != -1:
            payload["seed"] = params["seed"]

        # Add input image if provided
        input_image_data = self._process_input_image(params["input_image"])
        if input_image_data:
            payload["input_image"] = input_image_data

        return payload

    def _process_input_image(self, image_input: Any) -> str | None:
        """Process input image and convert to base64 data URI."""
        if not image_input:
            return None

        # Extract string value from input
        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        return self._convert_to_base64_data_uri(image_value)

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

    def _convert_to_base64_data_uri(self, image_value: str) -> str | None:
        """Convert image value to base64 data URI."""
        # If it's already a data URI, return it
        if image_value.startswith("data:image/"):
            return image_value

        # If it's a URL, download and convert to base64
        if image_value.startswith(("http://", "https://")):
            return self._download_and_encode_image(image_value)

        # Assume it's raw base64 without data URI prefix
        return f"data:image/png;base64,{image_value}"

    def _download_and_encode_image(self, url: str) -> str | None:
        """Download image from URL and encode as base64 data URI."""
        try:
            image_bytes = self._download_bytes_from_url(url)
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

    def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        """Poll the generations endpoint until ready."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = 120  # 10 minutes with 5s intervals
        poll_interval = 5

        for attempt in range(max_attempts):
            try:
                self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                response = requests.get(get_url, headers=headers, timeout=60)
                response.raise_for_status()
                result_json = response.json()

                status = result_json.get("status", "unknown")
                self._log(f"Status: {status}")

                if status == "Ready":
                    # Extract the image URL from result.sample
                    sample_url = result_json.get("result", {}).get("sample")
                    if sample_url:
                        self._handle_success(result_json, sample_url)
                    else:
                        self._log("No sample URL found in ready result")
                        self._set_safe_defaults()
                    return
                if status in ["Failed", "Error"]:
                    self._log(f"Generation failed with status: {status}")
                    self._set_safe_defaults()
                    return

                # Still processing, wait before next poll
                if attempt < max_attempts - 1:
                    time.sleep(poll_interval)

            except requests.exceptions.HTTPError as e:
                self._log(f"HTTP error while polling: {e.response.status_code} - {e.response.text}")
                if attempt == max_attempts - 1:
                    self._set_safe_defaults()
                    return
            except Exception as e:
                self._log(f"Error while polling: {e}")
                if attempt == max_attempts - 1:
                    self._set_safe_defaults()
                    return

        # Timeout reached
        self._log("Polling timed out waiting for result")
        self._set_safe_defaults()

    def _handle_success(self, response: dict[str, Any], image_url: str) -> None:
        """Handle successful generation result."""
        self.parameter_output_values["provider_response"] = response
        self._save_image_from_url(image_url)

    def _save_image_from_url(self, image_url: str) -> None:
        """Download and save the image from the provided URL."""
        try:
            self._log("Downloading image from URL")
            image_bytes = self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"flux_image_{int(time.time())}.jpg"
                from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved image to static storage as {filename}")
            else:
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
        except Exception as e:
            self._log(f"Failed to save image from URL: {e}")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image_url"] = None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL."""
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception:
            return None
        else:
            return resp.content
