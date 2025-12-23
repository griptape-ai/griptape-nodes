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
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["TopazImageEnhance"]

# Output format options
OUTPUT_FORMAT_OPTIONS = ["jpeg", "png", "webp"]

# Operation types
OPERATION_OPTIONS = [
    "enhance",
    "enhance-generative",
    "sharpen",
    "sharpen-generative",
    "denoise",
    "restore-generative",
    "lighting",
    "matting",
    "tool",
]

ENHANCE_MODELS = {
    "Standard V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "sharpen",
        "denoise",
        "fix_compression",
    ],
    "Low Resolution V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "sharpen",
        "denoise",
        "fix_compression",
    ],
    "CGI": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "sharpen",
        "denoise",
        "fix_compression",
    ],
    "High Fidelity V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "sharpen",
        "denoise",
        "fix_compression",
    ],
    "Text Refine": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "sharpen",
        "denoise",
        "fix_compression",
    ],
}

ENHANCE_GENERATIVE_MODELS = {
    "Redefine": ["prompt", "autoprompt", "creativity", "texture", "sharpen", "denoise"],
    "Recovery V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "detail",
    ],
    "Standard MAX": [],
    "Wonder": [],
}

SHARPEN_MODELS = {
    "Standard": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Strong": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
    ],
    "Lens Blur": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Lens Blur V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Motion Blur": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Natural": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Refocus": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_denoise",
    ],
    "Wildlife": ["denoise_strength", "sharpen_strength"],
    "Portrait": ["denoise_strength", "sharpen_strength"],
}

SHARPEN_GENERATIVE_MODELS = {
    "Super Focus V2": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "detail",
        "focus_boost",
    ],
}

DENOISE_MODELS = {
    "Normal": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_deblur",
        "original_detail",
    ],
    "Strong": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_deblur",
        "original_detail",
    ],
    "Extreme": [
        "face_enhancement",
        "face_enhancement_strength",
        "face_enhancement_creativity",
        "subject_detection",
        "strength",
        "minor_deblur",
        "original_detail",
    ],
}

RESTORE_GENERATIVE_MODELS = {
    "Dust-Scratch": [],
    "Dust-Scratch V2": ["grain", "grain_model", "grain_strength", "grain_density", "grain_size"],
}

LIGHTING_MODELS = {
    "Adjust": ["color_correction", "exposure", "highlight", "shadow"],
    "Adjust V2": ["exposure", "highlight", "shadow"],
    "White Balance": ["temperature", "opacity"],
    "Colorize": ["saturation"],
}

MATTING_MODELS = {
    "Object": ["mode"],
}

TOOL_MODELS = {
    "Transparency Upscale": [],
}

# Collect all unique parameter names from all model dictionaries
ALL_MODEL_PARAMS = frozenset(
    param
    for models_dict in (
        ENHANCE_MODELS,
        ENHANCE_GENERATIVE_MODELS,
        SHARPEN_MODELS,
        SHARPEN_GENERATIVE_MODELS,
        DENOISE_MODELS,
        RESTORE_GENERATIVE_MODELS,
        LIGHTING_MODELS,
        MATTING_MODELS,
        TOOL_MODELS,
    )
    for params_list in models_dict.values()
    for param in params_list
)

# Subject detection options
SUBJECT_DETECTION_OPTIONS = ["Foreground", "Background", "All"]

# Grain model options (for Dust-Scratch V2)
GRAIN_MODEL_OPTIONS = ["silver rich", "gaussian", "grey"]

# Matting mode options
MATTING_MODE_OPTIONS = ["alpha", "segmentation"]

OPERATION_MODELS = {
    "enhance": ENHANCE_MODELS,
    "enhance-generative": ENHANCE_GENERATIVE_MODELS,
    "sharpen": SHARPEN_MODELS,
    "sharpen-generative": SHARPEN_GENERATIVE_MODELS,
    "denoise": DENOISE_MODELS,
    "restore-generative": RESTORE_GENERATIVE_MODELS,
    "lighting": LIGHTING_MODELS,
    "matting": MATTING_MODELS,
    "tool": TOOL_MODELS,
}

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"


class TopazImageEnhance(SuccessFailureNode):
    """Enhance images using Topaz Labs models via Griptape model proxy.

    Inputs:
        - operation (str): Type of enhancement operation ("enhance", "denoise", or "sharpen")
        - model (str): Model to use for the selected operation
        - image_input (ImageArtifact/ImageUrlArtifact): Input image to process
        - output_format (str): Desired format of the output image ("jpeg", "png", or "webp")

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
        self.description = "Enhance images using Topaz Labs models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Operation selection
        self.add_parameter(
            ParameterString(
                name="operation",
                default_value="enhance",
                tooltip="Type of image enhancement operation",
                allow_output=False,
                traits={Options(choices=OPERATION_OPTIONS)},
            )
        )

        # Model selection - will be dynamically updated based on operation
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Standard V2",
                tooltip="Model to use for the selected operation",
                allow_output=False,
                traits={Options(choices=list(ENHANCE_MODELS.keys()))},
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

        # Sharpen parameter (for enhance operation)
        self.add_parameter(
            ParameterFloat(
                name="sharpen",
                default_value=0.0,
                tooltip="Additional sharpening (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Denoise parameter (for enhance operation)
        self.add_parameter(
            ParameterFloat(
                name="denoise",
                default_value=0.0,
                tooltip="Noise reduction amount (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Fix compression parameter (for enhance operation)
        self.add_parameter(
            ParameterFloat(
                name="fix_compression",
                default_value=0.0,
                tooltip="Fix lossy JPEG compression artifacts (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Denoise-specific: strength
        self.add_parameter(
            ParameterFloat(
                name="strength",
                default_value=0.5,
                tooltip="How aggressive the noise reduction should be (0.01-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.01,
                max_val=1.0,
                hide=True,
            )
        )

        # Denoise-specific: minor_deblur
        self.add_parameter(
            ParameterFloat(
                name="minor_deblur",
                default_value=0.1,
                tooltip="Mild sharpening applied after noise reduction (0.01-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.01,
                max_val=1.0,
                hide=True,
            )
        )

        # Denoise-specific: original_detail
        self.add_parameter(
            ParameterFloat(
                name="original_detail",
                default_value=0.5,
                tooltip="Restore fine texture lost during denoising (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
                hide=True,
            )
        )

        # Face enhancement toggle
        self.add_parameter(
            Parameter(
                name="face_enhancement",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable face-specific enhancements",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Face enhancement strength
        self.add_parameter(
            ParameterFloat(
                name="face_enhancement_strength",
                default_value=0.5,
                tooltip="How strong facial enhancement should be (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Face enhancement creativity
        self.add_parameter(
            ParameterFloat(
                name="face_enhancement_creativity",
                default_value=0.5,
                tooltip="Choose realistic (lower) or creative (higher) face recovery (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Subject detection
        self.add_parameter(
            ParameterString(
                name="subject_detection",
                default_value="All",
                tooltip="Where enhancements are applied (Foreground, Background, or All)",
                allow_output=False,
                traits={Options(choices=SUBJECT_DETECTION_OPTIONS)},
            )
        )

        # Sharpen-specific: minor_denoise
        self.add_parameter(
            ParameterFloat(
                name="minor_denoise",
                default_value=0.1,
                tooltip="Slight noise reduction applied after sharpening (0.01-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.01,
                max_val=1.0,
                hide=True,
            )
        )

        # Wildlife/Portrait-specific: denoise_strength
        self.add_parameter(
            ParameterFloat(
                name="denoise_strength",
                default_value=0.5,
                tooltip="Noise reduction strength for Wildlife/Portrait models (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
                hide=True,
            )
        )

        # Wildlife/Portrait-specific: sharpen_strength
        self.add_parameter(
            ParameterFloat(
                name="sharpen_strength",
                default_value=0.5,
                tooltip="Sharpening strength for Wildlife/Portrait models (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
                hide=True,
            )
        )

        # Generative model parameters

        # Prompt parameter (Redefine only)
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="A description of the resulting image (max 1024 characters)",
                multiline=True,
                placeholder_text="e.g., girl with red hair and blue eyes",
                allow_output=False,
                hide=True,
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
                hide=True,
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
                hide=True,
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
                hide=True,
            )
        )

        # Detail parameter (Recovery V2, Super Focus V2)
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

        # Focus boost parameter (Super Focus V2 only)
        self.add_parameter(
            ParameterFloat(
                name="focus_boost",
                default_value=0.5,
                tooltip="Boost focus strength (0.25-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.25,
                max_val=1.0,
                hide=True,
            )
        )

        # Grain parameters (Dust-Scratch V2 only)
        self.add_parameter(
            Parameter(
                name="grain",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Add film grain to the restored image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterString(
                name="grain_model",
                default_value="gaussian",
                tooltip="Type of grain to apply",
                allow_output=False,
                traits={Options(choices=GRAIN_MODEL_OPTIONS)},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterInt(
                name="grain_strength",
                default_value=30,
                tooltip="Strength of the grain effect (0-60)",
                allow_output=False,
                slider=True,
                min_val=0,
                max_val=60,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterInt(
                name="grain_density",
                default_value=30,
                tooltip="Density of the grain effect (0-60)",
                allow_output=False,
                slider=True,
                min_val=0,
                max_val=60,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterInt(
                name="grain_size",
                default_value=3,
                tooltip="Size of the grain particles (1-5)",
                allow_output=False,
                slider=True,
                min_val=1,
                max_val=5,
                hide=True,
            )
        )

        # Lighting parameters
        self.add_parameter(
            Parameter(
                name="color_correction",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Enable color correction",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="exposure",
                default_value=1.0,
                tooltip="Exposure adjustment (0.0-2.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=2.0,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="highlight",
                default_value=1.0,
                tooltip="Highlight adjustment (0.0-2.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=2.0,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="shadow",
                default_value=1.0,
                tooltip="Shadow adjustment (0.0-2.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=2.0,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="temperature",
                default_value=0.5,
                tooltip="Color temperature adjustment (0.01-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.01,
                max_val=1.0,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="opacity",
                default_value=1.0,
                tooltip="Effect opacity (0.01-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.01,
                max_val=1.0,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="saturation",
                default_value=0.5,
                tooltip="Saturation adjustment (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
                hide=True,
            )
        )

        # Matting mode parameter
        self.add_parameter(
            ParameterString(
                name="mode",
                default_value="alpha",
                tooltip="Matting output mode (alpha or segmentation)",
                allow_output=False,
                traits={Options(choices=MATTING_MODE_OPTIONS)},
                hide=True,
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

    def _update_visible_params_for_model(self, model_name: str) -> None:
        """Show/hide parameters based on the selected model's supported params."""
        operation = self.get_parameter_value("operation") or "enhance"
        models_dict = OPERATION_MODELS.get(operation, {})
        supported_params = set(models_dict.get(model_name, []))

        for param_name in ALL_MODEL_PARAMS:
            if param_name in supported_params:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

        if parameter.name == "operation":
            models_dict = OPERATION_MODELS.get(value, {})
            model_choices = list(models_dict.keys())
            if model_choices:
                first_model = model_choices[0]
                self._update_option_choices("model", model_choices, first_model)

        if parameter.name == "model" and value:
            self._update_visible_params_for_model(value)

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
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

        operation = params["operation"]
        model = params["model"]
        self._log(f"Processing image with Topaz {operation} using {model}")

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
        operation = self.get_parameter_value("operation") or "enhance"
        model = self.get_parameter_value("model") or "Standard V2"
        params = {
            "operation": operation,
            "model": model,
            "image_input": self.get_parameter_value("image_input"),
            "output_format": self.get_parameter_value("output_format"),
        }

        models_dict = OPERATION_MODELS.get(operation, {})
        supported_params = models_dict.get(model, [])

        for param_name in supported_params:
            params[param_name] = self.get_parameter_value(param_name)

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
        operation = params["operation"]
        proxy_url = urljoin(self._proxy_base, f"models/topaz-{operation}")

        self._log(f"Submitting request to Griptape model proxy for topaz-{operation}")
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

        operation = params.get("operation", "enhance")
        models_dict = OPERATION_MODELS.get(operation, {})
        supported_params = models_dict.get(params["model"], [])

        # Add supported parameters to payload
        for param_name in supported_params:
            if param_name in params:
                value = params[param_name]
                # Skip None values and handle face_enhancement specially
                if value is None:
                    continue
                # Only include face_enhancement_strength/creativity if face_enhancement is enabled
                if param_name in ("face_enhancement_strength", "face_enhancement_creativity") and not params.get(
                    "face_enhancement"
                ):
                    continue
                payload[param_name] = value

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
        max_attempts = 120  # 10 minutes with 5s intervals
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()

                    # Check if response is binary image data (JPEG starts with 0xff 0xd8)
                    content_type = response.headers.get("content-type", "")
                    if content_type.startswith("image/") or (response.content and response.content[:2] == b"\xff\xd8"):
                        self._log("Received binary image data directly from API")
                        await self._handle_binary_image_response(response.content)
                        return

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
                    self._set_safe_defaults()
                    error_msg = f"Failed to poll generation status: HTTP {e.response.status_code}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    return
                except Exception as e:
                    self._log(f"Error while polling: {e}")
                    self._set_safe_defaults()
                    error_msg = f"Failed to poll generation status: {e}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    return

            self._log("Polling timed out waiting for result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Image processing timed out after {max_attempts * poll_interval} seconds waiting for result.",
            )

    async def _handle_success(self, response: dict[str, Any], image_url: str) -> None:
        """Handle successful processing result."""
        self.parameter_output_values["provider_response"] = response
        await self._save_image_from_url(image_url)

    async def _handle_binary_image_response(self, image_bytes: bytes) -> None:
        """Handle binary image data returned directly from the API."""
        try:
            filename = f"topaz_enhanced_{int(time.time())}.jpg"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(image_bytes, filename)
            self.parameter_output_values["image_output"] = ImageUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved binary image to static storage as {filename}")
            self._set_status_results(
                was_successful=True, result_details=f"Image processed successfully and saved as {filename}."
            )
        except Exception as e:
            self._log(f"Failed to save binary image: {e}")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Image processing succeeded but failed to save: {e}",
            )

    async def _save_image_from_url(self, image_url: str) -> None:
        """Download and save the image from the provided URL."""
        try:
            self._log("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if image_bytes:
                filename = f"topaz_enhanced_{int(time.time())}.jpg"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image_output"] = ImageUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved image to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Image processed successfully and saved as {filename}."
                )
            else:
                self.parameter_output_values["image_output"] = ImageUrlArtifact(value=image_url)
                self._set_status_results(
                    was_successful=True,
                    result_details="Image processed successfully. Using provider URL (could not download image bytes).",
                )
        except Exception as e:
            self._log(f"Failed to save image from URL: {e}")
            self.parameter_output_values["image_output"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image processed successfully. Using provider URL (could not save to static storage: {e}).",
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
