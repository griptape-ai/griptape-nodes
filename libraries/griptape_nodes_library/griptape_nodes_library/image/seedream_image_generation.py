from __future__ import annotations

import json as _json
import logging
import time
from contextlib import suppress
from copy import deepcopy
from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedreamImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# Model mapping from user-facing names to API model IDs
MODEL_NAME_MAP = {
    "Seedream 4.5": "seedream-4-5-251128",
    "Seedream 4.0": "seedream-4-0-250828",
    "Seedream 3.0 T2I": "seedream-3-0-t2i-250415",
    "Seedream 3.0 I2I": "seededit-3-0-i2i-250628",
}

# Size options for different models (using friendly names)
SIZE_OPTIONS = {
    "Seedream 4.5": [
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
    "Seedream 4.0": [
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
    "Seedream 3.0 T2I": [
        "2048x2048",
        "2304x1728",
        "1728x2304",
        "2560x1440",
        "1440x2560",
        "2496x1664",
        "1664x2496",
        "3024x1296",
    ],
    "Seedream 3.0 I2I": [
        "adaptive",
    ],
}

# Maximum number of input images for models that support multiple images (using friendly names)
MAX_IMAGES_PER_MODEL = {
    "Seedream 4.5": 14,
    "Seedream 4.0": 10,
}


class SeedreamImageGeneration(GriptapeProxyNode):
    """Generate images using Seedream models via Griptape model proxy.

    Supports four models:
    - Seedream 4.5: Latest model with optional multiple image inputs (up to 14) and shorthand size options (2K, 4K)
      Minimum resolution: 2560x1440, Maximum resolution: 4096x4096
    - Seedream 4.0: Advanced model with optional multiple image inputs (up to 10) and shorthand size options (1K, 2K, 4K)
    - Seedream 3.0 T2I: Text-to-image only model with explicit size dimensions (WIDTHxHEIGHT format)
    - Seedream 3.0 I2I: Image-to-image editing model requiring single input image (WIDTHxHEIGHT format)

    Inputs:
        - model (str): Model selection (Seedream 4.5, Seedream 4.0, Seedream 3.0 T2I, Seedream 3.0 I2I)
        - prompt (str): Text prompt for image generation
        - image (ImageArtifact): Single input image (required for Seedream 3.0 I2I, hidden for other models)
        - images (list): Multiple input images (Seedream 4.5 supports up to 14, Seedream 4.0 up to 10)
        - size (str): Image size specification (dynamic options based on selected model)
        - seed (int): Random seed for reproducible results
        - max_images (int): Maximum number of images to generate (1-15, Seedream 4.0 and Seedream 4.5 only)
        - guidance_scale (float): Guidance scale (hidden for v4, visible for v3 models)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - image_url (ImageUrlArtifact): First generated image (always visible, backwards compatible)
        - image_url_2, image_url_3, ..., image_url_N (ImageUrlArtifact): Additional images (shown when API returns multiple images)
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Seedream models via Griptape model proxy"

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="Seedream 4.5",
                tooltip="Select the Seedream model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["Seedream 4.5", "Seedream 4.0", "Seedream 3.0 T2I", "Seedream 3.0 I2I"])},
            )
        )

        # Core parameters
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for image generation (max 600 words recommended)",
                multiline=True,
                placeholder_text="Describe the image you want to generate...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )

        # Optional single image input for Seedream 3.0 I2I (backwards compatibility)
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Input image (required for Seedream 3.0 I2I)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        # Multiple image inputs for Seedream 4.5/4.0 (up to 14/10 images)
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
                tooltip="Input images for Seedream (up to 14 for Seedream 4.5, 10 for Seedream 4.0)",
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
                traits={Options(choices=SIZE_OPTIONS["Seedream 4.5"])},
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

        # Max images parameter for Seedream 4.5 and Seedream 4.0
        self.add_parameter(
            ParameterInt(
                name="max_images",
                tooltip="Maximum number of images to generate (1-15, Seedream 4.0 and Seedream 4.5 only)",
                default_value=10,
                slider=True,
                min_val=1,
                max_val=15,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=False,
            )
        )

        # Guidance scale for Seedream 3.0 T2I
        self.add_parameter(
            Parameter(
                name="guidance_scale",
                input_types=["float"],
                type="float",
                default_value=2.5,
                tooltip="Guidance scale (Seedream 3.0 T2I only, default: 2.5)",
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
                hide=True,
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
                hide=True,
            )
        )

        # Create all image output parameters upfront (1-15) so they render in one block
        # First parameter is 'image_url' for backwards compatibility, rest are 'image_url_2' through 'image_url_15'
        # Only image_url is visible initially; others are shown when API returns multiple images
        for i in range(1, 16):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            self.add_parameter(
                Parameter(
                    name=param_name,
                    output_type="ImageUrlArtifact",
                    type="ImageUrlArtifact",
                    tooltip=f"Generated image {i}",
                    allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                    settable=False,
                    ui_options={"pulse_on_run": True, "hide": i > 1},
                )
            )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Initialize parameter visibility based on default model (Seedream 4.5)
        self._initialize_parameter_visibility()

    def _show_image_output_parameters(self, count: int) -> None:
        """Show image output parameters based on actual result count.

        All 15 image parameters are created during initialization but hidden except image_url.
        This method shows the appropriate number based on the API response.

        Args:
            count: Total number of images returned from API (1-15)
        """
        for i in range(1, 16):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            if i <= count:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model") or "Seedream 4.5"
        if default_model in ("Seedream 4.5", "Seedream 4.0"):
            # Hide single image input, show images list, show max_images, hide guidance scale
            self.hide_parameter_by_name("image")
            self.show_parameter_by_name("images")
            self.show_parameter_by_name("max_images")
            self.hide_parameter_by_name("guidance_scale")
        elif default_model == "Seedream 3.0 T2I":
            # Hide image inputs (not supported), hide max_images, show guidance scale
            self.hide_parameter_by_name("image")
            self.hide_parameter_by_name("images")
            self.hide_parameter_by_name("max_images")
            self.hide_parameter_by_name("guidance_scale")
        elif default_model == "Seedream 3.0 I2I":
            # Show single image input (required), hide images list, hide max_images, show guidance scale
            self.show_parameter_by_name("image")
            self.hide_parameter_by_name("images")
            self.hide_parameter_by_name("max_images")
            self.show_parameter_by_name("guidance_scale")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options and parameter visibility based on parameter changes."""
        if parameter.name == "model" and value in SIZE_OPTIONS:
            self._update_model_parameters(value)
        return super().after_value_set(parameter, value)

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Converts friendly model name to API model ID.
        """
        model = self.get_parameter_value("model") or "Seedream 4.5"
        return MODEL_NAME_MAP.get(model, model)

    def _update_model_parameters(self, model: str) -> None:
        """Update parameters and UI based on selected model."""
        new_choices = SIZE_OPTIONS[model]
        current_size = self.get_parameter_value("size")

        if model in ("Seedream 4.5", "Seedream 4.0"):
            self._configure_v4_models(model, new_choices, current_size)
        elif model == "Seedream 3.0 T2I":
            self._configure_v3_t2i_model(new_choices, current_size)
        elif model == "Seedream 3.0 I2I":
            self._configure_seededit_model(new_choices, current_size)

    def _configure_v4_models(self, model: str, new_choices: list[str], current_size: str) -> None:
        """Configure UI for Seedream 4.5 and Seedream 4.0 models."""
        self.hide_parameter_by_name("image")
        self.show_parameter_by_name("images")
        self.show_parameter_by_name("max_images")
        self.hide_parameter_by_name("guidance_scale")

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            default_size = "2K" if model == "Seedream 4.5" else "1K"
            default_size = default_size if default_size in new_choices else new_choices[0]
            self._update_option_choices("size", new_choices, default_size)

    def _configure_v3_t2i_model(self, new_choices: list[str], current_size: str) -> None:
        """Configure UI for Seedream 3.0 T2I model."""
        self.hide_parameter_by_name("image")
        self.hide_parameter_by_name("images")
        self.hide_parameter_by_name("max_images")
        self.show_parameter_by_name("guidance_scale")
        self.set_parameter_value("guidance_scale", 2.5)

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            self._update_option_choices("size", new_choices, "2048x2048")

    def _configure_seededit_model(self, new_choices: list[str], current_size: str) -> None:
        """Configure UI for Seedream 3.0 I2I model."""
        self.show_parameter_by_name("image")
        self.hide_parameter_by_name("images")
        self.hide_parameter_by_name("max_images")
        self.show_parameter_by_name("guidance_scale")

        image_param = self.get_parameter_by_name("image")
        if image_param:
            image_param.tooltip = "Input image (required for Seedream 3.0 I2I)"
            image_param.ui_options["display_name"] = "Input Image"

        self.set_parameter_value("guidance_scale", 2.5)

        if current_size in new_choices:
            self._update_option_choices("size", new_choices, current_size)
        else:
            self._update_option_choices("size", new_choices, "adaptive")

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the result and set output parameters.

        Args:
            result_json: The JSON response from the /result endpoint
            generation_id: The generation ID for this request
        """
        # Extract image data
        data = result_json.get("data", [])
        if not data:
            self._log("No image data in result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no image data was found in the response.",
            )
            return

        # Process all images from the response
        image_artifacts = []
        for idx, image_data in enumerate(data):
            image_url = image_data.get("url")
            if not image_url:
                self._log(f"No URL found for image {idx}")
                continue

            artifact = await self._save_single_image_from_url(image_url, generation_id, idx)
            if artifact:
                image_artifacts.append(artifact)

        if not image_artifacts:
            self._log("No images could be saved")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no image URLs were found in the response.",
            )
            return

        # Show the appropriate number of image output parameters based on actual image count
        self._show_image_output_parameters(len(image_artifacts))

        # Set individual image output parameters
        for idx, artifact in enumerate(image_artifacts, start=1):
            param_name = "image_url" if idx == 1 else f"image_url_{idx}"
            self.parameter_output_values[param_name] = artifact

        # Set success status
        count = len(image_artifacts)
        filenames = [artifact.name for artifact in image_artifacts]
        if count == 1:
            details = f"Image generated successfully and saved as {filenames[0]}."
        else:
            details = f"Generated {count} images successfully: {', '.join(filenames)}."
        self._set_status_results(was_successful=True, result_details=details)

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

    def _get_parameters(self) -> dict[str, Any]:
        params = {
            "model": self.get_parameter_value("model") or "Seedream 4.5",
            "prompt": self.get_parameter_value("prompt") or "",
            "image": self.get_parameter_value("image"),
            "size": self.get_parameter_value("size") or "2K",
            "seed": self.get_parameter_value("seed") or -1,
            "guidance_scale": self.get_parameter_value("guidance_scale") or 2.5,
            "watermark": False,
        }

        # Get image list for Seedream 4.5 and Seedream 4.0
        if params["model"] in ("Seedream 4.5", "Seedream 4.0"):
            params["images"] = self.get_parameter_list_value("images") or []
            params["sequential_image_generation"] = "auto"
            params["sequential_image_generation_options"] = {
                "max_images": self.get_parameter_value("max_images"),
            }

        return params

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Seedream API (without model field)."""
        params = self._get_parameters()
        model = params["model"]

        payload = {
            "model": self._get_api_model_id(),
            "prompt": params["prompt"],
            "size": params["size"],
            "response_format": "url",
            "watermark": params["watermark"],
        }

        # Add seed if not -1
        if params["seed"] != -1:
            payload["seed"] = params["seed"]

        # Model-specific parameters
        if model in ("Seedream 4.5", "Seedream 4.0"):
            # Add sequential image generation configuration
            payload["sequential_image_generation"] = params["sequential_image_generation"]
            payload["sequential_image_generation_options"] = params["sequential_image_generation_options"]

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

        elif model == "Seedream 3.0 T2I":
            # Add guidance scale for v3 t2i
            payload["guidance_scale"] = params["guidance_scale"]

        elif model == "Seedream 3.0 I2I":
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

    async def _save_single_image_from_url(
        self, image_url: str, generation_id: str | None = None, index: int = 0
    ) -> ImageUrlArtifact | None:
        """Download and save a single image from the provided URL.

        Args:
            image_url: URL of the image to download
            generation_id: Optional generation ID for filename
            index: Index of the image in multi-image response

        Returns:
            ImageUrlArtifact with saved image, or None if download/save fails
        """
        try:
            self._log(f"Downloading image {index} from URL")
            image_bytes = await self._download_bytes_from_url(image_url)
            if not image_bytes:
                self._log(f"Could not download image {index}, using provider URL")
                return ImageUrlArtifact(value=image_url)

            if generation_id:
                filename = f"seedream_image_{generation_id}_{index}.jpg"
            else:
                filename = f"seedream_image_{int(time.time())}_{index}.jpg"

            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(image_bytes, filename)
            self._log(f"Saved image {index} to static storage as {filename}")
            return ImageUrlArtifact(value=saved_url, name=filename)

        except Exception as e:
            self._log(f"Failed to save image {index} from URL: {e}")
            return ImageUrlArtifact(value=image_url)

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from failed/errored generation response.

        Tries Seedream-specific error patterns first, then falls back to base implementation.

        Args:
            response_json: The JSON response from the generation status endpoint

        Returns:
            str: A formatted error message to display to the user
        """
        if not response_json:
            return super()._extract_error_message(response_json)

        # Check for v2 API status_detail first (for FAILED/ERROR statuses)
        status_detail = response_json.get("status_detail")
        if status_detail:
            error_msg = self._format_status_detail_error(status_detail)
            if error_msg:
                return f"{self.name} {error_msg}"

        # Try to extract from provider response (legacy pattern)
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))
        if parsed_provider_response:
            provider_error = parsed_provider_response.get("error")
            if provider_error:
                if isinstance(provider_error, dict):
                    error_message = provider_error.get("message", "")
                    details = f"{self.name} {error_message}"
                    if error_code := provider_error.get("code"):
                        details += f"\nError Code: {error_code}"
                    if error_type := provider_error.get("type"):
                        details += f"\nError Type: {error_type}"
                    return details
                return f"{self.name} Provider error: {provider_error}"

        # Fall back to base implementation
        return super()._extract_error_message(response_json)

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

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None

        # Clear all image output parameters (all 15 are created during initialization)
        for i in range(1, 16):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            self.parameter_output_values[param_name] = None
