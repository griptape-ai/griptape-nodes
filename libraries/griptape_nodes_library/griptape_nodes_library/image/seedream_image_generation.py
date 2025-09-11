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
from griptape_nodes.traits.options import Options

logger = logging.getLogger(__name__)

__all__ = ["SeedreamImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model mapping from human-friendly names to API model IDs
MODEL_MAPPING = {
    "seedream-4.0": "seedream-4-0-250828",
    "seedream-3.0-t2i": "seedream-3-0-t2i-250415",
    "seededit-3.0-i2i": "seededit-3-0-i2i-250628",
}

# Size options for different models
SIZE_OPTIONS = {
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


class SeedreamImageGeneration(DataNode):
    """Generate images using Seedream models via Griptape model proxy.

    Supports three models:
    - seedream-4.0: Advanced model with optional image input and shorthand size options (1K, 2K, 4K)
    - seedream-3.0-t2i: Text-to-image only model with explicit size dimensions (WIDTHxHEIGHT format)
    - seededit-3.0-i2i: Image-to-image editing model requiring input image (WIDTHxHEIGHT format)

    Inputs:
        - model (str): Model selection (seedream-4.0, seedream-3.0-t2i, seededit-3.0-i2i)
        - prompt (str): Text prompt for image generation
        - image (ImageArtifact): Input image (optional for v4, required for seededit i2i, hidden for t2i)
        - size (str): Image size specification (dynamic options based on selected model)
        - seed (int): Random seed for reproducible results
        - guidance_scale (float): Guidance scale (hidden for v4, visible for v3 models)

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
        self.description = "Generate images using Seedream models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/models/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="seedream-4.0",
                tooltip="Select the Seedream model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["seedream-4.0", "seedream-3.0-t2i", "seededit-3.0-i2i"])},
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

        # Optional image input for seedream-4.0 and seededit-3.0-i2i
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Input image (required for seededit-3.0-i2i, optional for seedream-4.0)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Size parameter - will be updated dynamically based on model selection
        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="2048x2048",
                tooltip="Image size specification",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SIZE_OPTIONS["seedream-4.0"])},
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options and parameter visibility based on model selection."""
        if parameter.name == "model" and value in SIZE_OPTIONS:
            new_choices = SIZE_OPTIONS[value]

            # Set appropriate parameters for each model
            if value == "seedream-4.0":
                # Show image input (optional), hide guidance scale
                self.show_parameter_by_name("image")
                self.hide_parameter_by_name("guidance_scale")
                # Update size choices and set default to 2K for v4
                default_size = "2K" if "2K" in new_choices else new_choices[0]
                self._update_option_choices("size", new_choices, default_size)

            elif value == "seedream-3.0-t2i":
                # Hide image input (not supported), show guidance scale
                self.hide_parameter_by_name("image")
                self.show_parameter_by_name("guidance_scale")
                # Set default guidance scale
                self.set_parameter_value("guidance_scale", 2.5)
                # Update size choices and set default to 2048x2048 for v3 t2i
                self._update_option_choices("size", new_choices, "2048x2048")

            elif value == "seededit-3.0-i2i":
                # Show image input (required), show guidance scale
                self.show_parameter_by_name("image")
                self.show_parameter_by_name("guidance_scale")
                # Set default guidance scale
                self.set_parameter_value("guidance_scale", 2.5)
                # Update size choices and set default to adaptive for seededit
                self._update_option_choices("size", new_choices, "adaptive")

        return super().after_value_set(parameter, value)

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

        response = self._submit_request(params, headers)
        if response:
            self._handle_response(response)
        else:
            self._set_safe_defaults()

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "model": self.get_parameter_value("model") or "seedream-4.0",
            "prompt": self.get_parameter_value("prompt") or "",
            "image": self.get_parameter_value("image"),
            "size": self.get_parameter_value("size") or "2048x2048",
            "seed": self.get_parameter_value("seed") or -1,
            "guidance_scale": self.get_parameter_value("guidance_scale") or 2.5,
            "watermark": False,
        }

    def _validate_api_key(self) -> str:
        api_key = self.get_config_value(service=self.SERVICE_NAME, value=self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any] | None:
        payload = self._build_payload(params)
        # Map friendly model name to API model ID
        api_model_id = MODEL_MAPPING.get(params["model"], params["model"])
        proxy_url = urljoin(self._proxy_base, api_model_id)

        self._log(f"Submitting request to Griptape model proxy with model: {params['model']}")
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
        else:
            return response_json

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
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
        if model == "seedream-4.0":
            # Add input image if provided for v4
            image_data = self._process_input_image(params["image"])
            if image_data:
                payload["image"] = image_data

        elif model == "seedream-3.0-t2i":
            # Add guidance scale for v3 t2i
            payload["guidance_scale"] = params["guidance_scale"]

        elif model == "seededit-3.0-i2i":
            # Add guidance scale and required image for seededit
            payload["guidance_scale"] = params["guidance_scale"]
            image_data = self._process_input_image(params["image"])
            if image_data:
                payload["image"] = image_data

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
            # Redact base64 image data
            if "image" in sanitized_payload:
                image_data = sanitized_payload["image"]
                if isinstance(image_data, str) and image_data.startswith("data:image/"):
                    parts = image_data.split(",", 1)
                    header = parts[0] if parts else "data:image/"
                    b64_len = len(parts[1]) if len(parts) > 1 else 0
                    sanitized_payload["image"] = f"{header},<base64 data length={b64_len}>"

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _handle_response(self, response: dict[str, Any]) -> None:
        self.parameter_output_values["provider_response"] = response

        # Extract generation ID if available
        generation_id = response.get("id", response.get("created", ""))
        self.parameter_output_values["generation_id"] = str(generation_id)

        # Extract image data (expecting single image)
        data = response.get("data", [])
        if not data:
            self._log("No image data in response")
            self.parameter_output_values["image_url"] = None
            return

        # Take first image from response
        image_data = data[0]

        # Always using URL format
        image_url = image_data.get("url")
        if image_url:
            self._save_image_from_url(image_url)
        else:
            self._log("No image URL in response")
            self.parameter_output_values["image_url"] = None

    def _save_image_from_url(self, image_url: str) -> None:
        try:
            self._log("Downloading image from URL")
            image_bytes = self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"seedream_image_{int(time.time())}.jpg"
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
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image_url"] = None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception:
            return None
        else:
            return resp.content
