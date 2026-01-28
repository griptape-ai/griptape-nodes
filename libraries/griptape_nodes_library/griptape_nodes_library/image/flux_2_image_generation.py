from __future__ import annotations

import base64
import json as _json
import logging
from contextlib import suppress
from copy import deepcopy
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.utils.artifact_normalization import normalize_artifact_list
from griptape_nodes.utils.url_utils import is_url_or_path
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import (
    convert_image_value_to_base64_data_uri,
    read_image_from_file_path,
    resolve_localhost_url_to_path,
)

logger = logging.getLogger("griptape_nodes")

__all__ = ["Flux2ImageGeneration"]

# Maximum number of input images supported
MAX_INPUT_IMAGES = 8

# Image dimension constants
DEFAULT_IMAGE_SIZE = 1024
IMAGE_DIMENSION_STEP = 16
MAX_IMAGE_DIMENSION = 8192  # Any image wider than this will be >4MP anyways

# Output format options
OUTPUT_FORMAT_OPTIONS = ["jpeg", "png"]

# Model mapping from user-friendly names to API model IDs
MODEL_MAPPING = {
    "Flux.2 [pro]": "flux-2-pro",
    "Flux.2 [flex]": "flux-2-flex",
    "Flux.2 [max]": "flux-2-max",
    "Flux.2 [klein] 4B": "flux-2-klein-4b",
    "Flux.2 [klein] 9B": "flux-2-klein-9b",
}
MODEL_OPTIONS = list(MODEL_MAPPING.keys())
DEFAULT_MODEL = MODEL_OPTIONS[0]

# Safety tolerance options
SAFETY_TOLERANCE_OPTIONS = ["least restrictive", "moderate", "most restrictive"]

MAX_STEPS_FLEX = 50
MIN_STEPS_FLEX = 1
MAX_GUIDANCE_FLEX = 10.0
MIN_GUIDANCE_FLEX = 1.5
DEFAULT_GUIDANCE_FLEX = 4.5


class Flux2ImageGeneration(GriptapeProxyNode):
    """Generate images using Flux-2 models via Griptape model proxy.

    Inputs:
        - model (str): Flux model to use (default: "Flux 2 [pro]")
        - prompt (str): Text description of the desired image
        - input_images (list): Optional input images for image-to-image generation
        - width (int): Output width in pixels. Must be a multiple of 16. (default: 1024)
        - height (int): Output height in pixels. Must be a multiple of 16. (default: 1024)
        - force_output_dimension (bool): When enabled, automatically adjusts width and height to the nearest multiple of 16 (default: False)
        - randomize_seed (bool): If true, randomize the seed on each run (default: False)
        - seed (int): Random seed for reproducible results (default: 42)
        - output_format (str): Desired format of the output image ("jpeg" or "png")
        - safety_tolerance (str): Content moderation preset ("least restrictive", "moderate", or "most restrictive")
        - steps (int): [flex only] Number of inference steps. Maximum: 50, default: 50. Higher = more detail, slower.
        - guidance (float): [flex only] Guidance scale. Controls how closely the output follows the prompt. Minimum: 1.5, maximum: 10, default: 4.5. Higher = closer prompt adherence.

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_url (ImageUrlArtifact): Generated image as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Flux models via Griptape model proxy"

        # Model selection
        self.add_parameter(
            ParameterString(
                name="model",
                default_value=DEFAULT_MODEL,
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
            ParameterList(
                name="input_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                ],
                default_value=[],
                tooltip="Optional input images for image-to-image generation (supports up to 20MB or 20 megapixels)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"expander": True, "display_name": "Input Images"},
            )
        )
        # Width parameter
        self.add_parameter(
            ParameterInt(
                name="width",
                default_value=DEFAULT_IMAGE_SIZE,
                tooltip="Output width in pixels. Must be a multiple of 16. Total image size cannot exceed 4MP.",
                allow_output=False,
                min_val=IMAGE_DIMENSION_STEP,
                max_val=MAX_IMAGE_DIMENSION,
                step=IMAGE_DIMENSION_STEP,
            )
        )

        # Height parameter
        self.add_parameter(
            ParameterInt(
                name="height",
                default_value=DEFAULT_IMAGE_SIZE,
                tooltip="Output height in pixels. Must be a multiple of 16. Total image size cannot exceed 4MP.",
                allow_output=False,
                min_val=IMAGE_DIMENSION_STEP,
                max_val=MAX_IMAGE_DIMENSION,
                step=IMAGE_DIMENSION_STEP,
            )
        )

        # Force output dimension parameter
        self.add_parameter(
            ParameterBool(
                name="force_output_dimension",
                default_value=False,
                tooltip="When enabled, automatically adjusts width and height to the nearest multiple of 16.\n(Required for Flux.2 [flex] model to work correctly.)",
                allow_output=False,
            )
        )

        # Seed parameter (using SeedParameter component)
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
        # Steps parameter
        self.add_parameter(
            ParameterInt(
                name="steps",
                default_value=MAX_STEPS_FLEX,
                tooltip="Number of inference steps",
                allow_output=False,
                slider=True,
                min_val=1,
                max_val=MAX_STEPS_FLEX,
                hide=True,
            )
        )

        # Guidance parameter
        self.add_parameter(
            ParameterFloat(
                name="guidance",
                default_value=DEFAULT_GUIDANCE_FLEX,
                tooltip="Guidance scale",
                allow_output=False,
                slider=True,
                min_val=MIN_GUIDANCE_FLEX,
                max_val=MAX_GUIDANCE_FLEX,
                hide=True,
            )
        )

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allow_input=False,
                allow_property=False,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterImage(
                name="image_url",
                tooltip="Generated image as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                pulse_on_run=True,
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        self._seed_parameter.after_value_set(parameter, value)

        # Convert string paths to ImageUrlArtifact by uploading to static storage
        if parameter.name == "input_images" and isinstance(value, list):
            updated_list = normalize_artifact_list(value, ImageUrlArtifact, accepted_types=(ImageArtifact,))
            if updated_list != value:
                self.set_parameter_value("input_images", updated_list)

        if parameter.name == "model":
            # Map friendly name to API model ID
            model_value = str(value) if value is not None else ""
            api_model_id = MODEL_MAPPING.get(model_value, model_value)
            if api_model_id == "flux-2-flex":
                self.show_parameter_by_name("steps")
                self.show_parameter_by_name("guidance")
            else:
                self.hide_parameter_by_name("steps")
                self.hide_parameter_by_name("guidance")

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Maps friendly model names to API model IDs.

        Returns:
            str: The API model ID to use in the API request
        """
        model = self.get_parameter_value("model") or DEFAULT_MODEL
        model_str = str(model) if model is not None else DEFAULT_MODEL
        return MODEL_MAPPING.get(model_str, model_str)

    def _parse_safety_tolerance(self, value: str | None) -> int:
        """Parse safety tolerance integer from preset string value.

        Args:
            value: One of "least restrictive", "moderate", or "most restrictive"

        Returns:
            Integer value: 5 for least restrictive, 2 for moderate, 0 for most restrictive

        Raises:
            ValueError: If value is None or not one of the expected options
        """
        if not value:
            msg = "safety_tolerance cannot be None or empty"
            raise ValueError(msg)

        if value == "most restrictive":
            return 0
        if value == "moderate":
            return 2
        if value == "least restrictive":
            return 5

        msg = f"Invalid safety_tolerance value: '{value}'. Must be one of: {SAFETY_TOLERANCE_OPTIONS}"
        raise ValueError(msg)

    def _round_to_nearest_multiple_of_16(self, value: int) -> int:
        """Round a value to the nearest multiple of 16.

        Args:
            value: The value to round

        Returns:
            The nearest multiple of 16
        """
        return round(value / IMAGE_DIMENSION_STEP) * IMAGE_DIMENSION_STEP

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Flux image generation.

        This method builds the payload without the model field (handled separately).

        Returns:
            dict: The request payload to send to the API
        """
        # Preprocess seed
        self._seed_parameter.preprocess()

        # Get parameters
        prompt = self.get_parameter_value("prompt") or ""
        output_format = self.get_parameter_value("output_format") or "jpeg"
        safety_tolerance_str = self.get_parameter_value("safety_tolerance")
        seed = self._seed_parameter.get_seed()
        width = self.get_parameter_value("width") or DEFAULT_IMAGE_SIZE
        height = self.get_parameter_value("height") or DEFAULT_IMAGE_SIZE

        # Adjust dimensions to be divisible by 16 if force_output_dimension is enabled
        force_output_dimension = self.get_parameter_value("force_output_dimension") or False
        if force_output_dimension:
            original_width = width
            original_height = height
            width = self._round_to_nearest_multiple_of_16(width)
            height = self._round_to_nearest_multiple_of_16(height)
            # Log the adjustment if dimensions changed
            if original_width != width or original_height != height:
                self._log(
                    f"Adjusted dimensions to be divisible by 16: {original_width}x{original_height} -> {width}x{height}"
                )

        # Build base payload
        payload = {
            "prompt": prompt,
            "output_format": output_format,
            "safety_tolerance": self._parse_safety_tolerance(safety_tolerance_str),
            "seed": seed,
            "width": width,
            "height": height,
        }

        # Add steps and guidance for flex model
        api_model_id = self._get_api_model_id()
        if api_model_id == "flux-2-flex":
            payload["steps"] = self.get_parameter_value("steps") or MAX_STEPS_FLEX
            payload["guidance"] = self.get_parameter_value("guidance") or DEFAULT_GUIDANCE_FLEX

        # Add input images if provided (input_image, input_image_2, ..., input_image_9)
        input_images_list = self.get_parameter_list_value("input_images") or []
        if not isinstance(input_images_list, list):
            input_images_list = [input_images_list] if input_images_list else []

        # Normalize string paths to ImageUrlArtifact during processing
        # (handles cases where values come from connections and bypass after_value_set)
        input_images_list = normalize_artifact_list(
            input_images_list, ImageUrlArtifact, accepted_types=(ImageArtifact,)
        )

        image_index = 0
        for image_input in input_images_list:
            if image_index >= MAX_INPUT_IMAGES:
                break

            input_image_data = await self._process_input_image(image_input)
            if input_image_data:
                if image_index == 0:
                    payload["input_image"] = input_image_data
                else:
                    payload[f"input_image_{image_index + 1}"] = input_image_data
                image_index += 1

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the Flux result and set output parameters.

        Args:
            result_json: The JSON response from the /result endpoint
            generation_id: The generation ID for this request
        """
        # Extract image URL from BFL response format (result.sample)
        sample_url = result_json.get("result", {}).get("sample")
        if not sample_url:
            self._log("No sample URL found in result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no image URL was found in the response.",
            )
            return

        # Download and save the image using generation_id in filename
        try:
            self._log("Downloading image from URL")
            image_bytes = await self._download_bytes_from_url(sample_url)
            if image_bytes:
                filename = f"flux_image_{generation_id}.jpg"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename, use_direct_save=True)
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved image to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Image generated successfully and saved as {filename}."
                )
            else:
                self.parameter_output_values["image_url"] = ImageUrlArtifact(value=sample_url)
                self._set_status_results(
                    was_successful=True,
                    result_details="Image generated successfully. Using provider URL (could not download image bytes).",
                )
        except Exception as e:
            self._log(f"Failed to save image from URL: {e}")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=sample_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image generated successfully. Using provider URL (could not save to static storage: {e}).",
            )

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
            # Resolve localhost URLs to workspace paths
            return resolve_localhost_url_to_path(image_input)

        try:
            # ImageUrlArtifact: .value holds URL string
            if hasattr(image_input, "value"):
                value = getattr(image_input, "value", None)
                if isinstance(value, str):
                    # Resolve localhost URLs to workspace paths
                    return resolve_localhost_url_to_path(value)

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
        if is_url_or_path(image_value):
            return await self._download_and_encode_image(image_value)

        # Try to read as file path first (works cross-platform)
        file_path = read_image_from_file_path(image_value, self.name)
        if file_path:
            return file_path

        # Use utility function to handle raw base64
        return convert_image_value_to_base64_data_uri(image_value, self.name)

    async def _download_and_encode_image(self, url: str) -> str | None:
        """Download image from URL and encode as base64 data URI."""
        try:
            image_bytes = await self._download_bytes_from_url(url)
            if image_bytes:
                b64_string = base64.b64encode(image_bytes).decode("utf-8")
                return f"data:image/png;base64,{b64_string}"
        except Exception as e:
            self._log(f"Failed to download image from URL {url}: {e}")
        return None

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = deepcopy(payload)
            # Redact base64 input image data for all input images (input_image, input_image_2, ..., input_image_9)
            for key in list(sanitized_payload.keys()):
                if key == "input_image" or (key.startswith("input_image_") and key[12:].isdigit()):
                    image_data = sanitized_payload[key]
                    if isinstance(image_data, str) and image_data.startswith("data:image/"):
                        parts = image_data.split(",", 1)
                        header = parts[0] if parts else "data:image/"
                        b64_len = len(parts[1]) if len(parts) > 1 else 0
                        sanitized_payload[key] = f"{header},<base64 data length={b64_len}>"

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image_url"] = None
