from __future__ import annotations

import base64
import json as _json
import logging
import os
import re
import time
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import get_image_dimensions_from_artifact

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedreamImageGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100


class Model(StrEnum):
    """Seedream model identifiers."""

    SEEDREAM_4_0 = "seedream-4.0"
    SEEDREAM_3_0_T2I = "seedream-3.0-t2i"
    SEEDEDIT_3_0_I2I = "seededit-3.0-i2i"


class ValidationSeverity(StrEnum):
    """Severity levels for validation messages."""

    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationMessage:
    """A validation message with severity level."""

    severity: ValidationSeverity
    message: str


@dataclass
class SizeValidation:
    """Image size validation constraints for a model."""

    min_dimension: int
    max_dimension: int
    aspect_ratio_min: float
    aspect_ratio_max: float
    allows_shorthand: bool


@dataclass
class ModelConfig:
    """Complete configuration for a Seedream model."""

    api_id: str
    size_validation: SizeValidation
    size_options: list[str]
    max_images: int | None  # None means images not supported, int means max count
    min_images: int | None  # None or 0 means optional, int > 0 means required minimum
    prompt_max_tokens: int
    seed_range: tuple[int, int]


# Model configurations
MODEL_CONFIG: dict[Model, ModelConfig] = {
    Model.SEEDREAM_4_0: ModelConfig(
        api_id="seedream-4-0-250828",
        size_validation=SizeValidation(
            min_dimension=1024,
            max_dimension=4096,
            aspect_ratio_min=1 / 3,
            aspect_ratio_max=3.0,
            allows_shorthand=True,
        ),
        size_options=[
            "1K",
            "2K",
            "4K",
            "1024x1024",
            "2048x2048",
            "4096x4096",
            "1280x720",
            "1920x1080",
            "2560x1440",
            "720x1280",
            "1080x1920",
            "1440x2560",
            "1152x864",
            "1536x1152",
            "2048x1536",
            "864x1152",
            "1152x1536",
            "1536x2048",
            "1512x648",
            "2560x1080",
            "3440x1440",
        ],
        max_images=10,  # Supports up to 10 reference images
        min_images=None,  # Images are optional for v4
        prompt_max_tokens=512,
        seed_range=(-1, 2147483647),
    ),
    Model.SEEDREAM_3_0_T2I: ModelConfig(
        api_id="seedream-3-0-t2i-250415",
        size_validation=SizeValidation(
            min_dimension=512,
            max_dimension=2048,
            aspect_ratio_min=1 / 3,
            aspect_ratio_max=3.0,
            allows_shorthand=False,
        ),
        size_options=[
            "1024x1024",
            "2048x2048",
            "1152x864",
            "864x1152",
            "1280x720",
            "720x1280",
            "1248x832",
            "832x1248",
            "1512x648",
        ],
        max_images=None,  # Does not support image inputs
        min_images=None,  # No images required (text-to-image only)
        prompt_max_tokens=300,
        seed_range=(-1, 2147483647),
    ),
    Model.SEEDEDIT_3_0_I2I: ModelConfig(
        api_id="seededit-3-0-i2i-250628",
        size_validation=SizeValidation(
            min_dimension=512,
            max_dimension=4096,
            aspect_ratio_min=1 / 3,
            aspect_ratio_max=3.0,
            allows_shorthand=False,
        ),
        size_options=["adaptive"],
        max_images=1,  # Requires exactly 1 input image
        min_images=1,  # Image is required for i2i
        prompt_max_tokens=300,
        seed_range=(-1, 2147483647),
    ),
}


class SeedreamImageGeneration(SuccessFailureNode):
    """Generate images using Seedream models via Griptape model proxy.

    Supports three models:
    - seedream-4.0: Advanced model with optional multiple image inputs (up to 10) and shorthand size options (1K, 2K, 4K)
    - seedream-3.0-t2i: Text-to-image only model with explicit size dimensions (WIDTHxHEIGHT format)
    - seededit-3.0-i2i: Image-to-image editing model requiring single input image (WIDTHxHEIGHT format)

    Inputs:
        - model (str): Model selection (seedream-4.0, seedream-3.0-t2i, seededit-3.0-i2i)
        - prompt (str): Text prompt for image generation
        - image (ImageArtifact): Single input image (required for seededit-3.0-i2i, hidden for other models)
        - images (list): Multiple input images (seedream-4.0 only, up to 10 images total)
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
        self._proxy_base = urljoin(api_base, "proxy/models/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value=Model.SEEDREAM_4_0.value,
                tooltip="Select the Seedream model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[Model.SEEDREAM_4_0.value, Model.SEEDREAM_3_0_T2I.value, Model.SEEDEDIT_3_0_I2I.value]
                    )
                },
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

        # Multiple image inputs for seedream-4.0 (up to 10 images)
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
                tooltip="Input images for seedream-4.0 (up to 10 images total)",
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
                default_value="1K",
                tooltip="Image size specification",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_CONFIG[Model.SEEDREAM_4_0].size_options)},
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

        # Add validation error message (initially hidden)
        self.add_node_element(
            ParameterMessage(
                name="validation_errors",
                variant="error",
                value="",
                title="Validation Errors",
            )
        )
        self.hide_message_by_name("validation_errors")

        # Add validation warning message (initially hidden)
        self.add_node_element(
            ParameterMessage(
                name="validation_warnings",
                variant="warning",
                value="",
                title="Validation Warnings",
            )
        )
        self.hide_message_by_name("validation_warnings")

        # Initialize parameter visibility based on default model (seedream-4.0)
        self._initialize_parameter_visibility()

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model")
        if not default_model:
            msg = f"{self.name} - Model parameter is not set"
            raise ValueError(msg)

        match default_model:
            case Model.SEEDREAM_4_0:
                # Hide single image input, show images list, hide guidance scale
                self.hide_parameter_by_name("image")
                self.show_parameter_by_name("images")
                self.hide_parameter_by_name("guidance_scale")
            case Model.SEEDREAM_3_0_T2I:
                # Hide image inputs (not supported), show guidance scale
                self.hide_parameter_by_name("image")
                self.hide_parameter_by_name("images")
                self.show_parameter_by_name("guidance_scale")
            case Model.SEEDEDIT_3_0_I2I:
                # Show single image input (required), hide images list, show guidance scale
                self.show_parameter_by_name("image")
                self.hide_parameter_by_name("images")
                self.show_parameter_by_name("guidance_scale")
            case _:
                msg = f"Unknown model: {default_model}"
                raise ValueError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Update size options and parameter visibility based on model selection."""
        if parameter.name == "model":
            # Convert string value to Model enum if needed
            if isinstance(value, str):
                try:
                    model_enum = Model(value)
                except ValueError:
                    msg = f"Unknown model: {value}"
                    raise ValueError(msg) from None
            else:
                model_enum = value

            if model_enum not in MODEL_CONFIG:
                msg = f"Model {model_enum} is not configured in MODEL_CONFIG"
                raise ValueError(msg)

            new_choices = MODEL_CONFIG[model_enum].size_options
            current_size = self.get_parameter_value("size")

            # Set appropriate parameters for each model
            match model_enum:
                case Model.SEEDREAM_4_0:
                    # Hide single image input, show images list, hide guidance scale
                    self.hide_parameter_by_name("image")
                    self.show_parameter_by_name("images")
                    self.hide_parameter_by_name("guidance_scale")
                    # Update size choices and preserve current size if valid, otherwise default to 1K for v4
                    if current_size in new_choices:
                        self._update_option_choices("size", new_choices, current_size)
                    else:
                        default_size = "1K" if "1K" in new_choices else new_choices[0]
                        self._update_option_choices("size", new_choices, default_size)

                case Model.SEEDREAM_3_0_T2I:
                    # Hide image inputs (not supported), show guidance scale
                    self.hide_parameter_by_name("image")
                    self.hide_parameter_by_name("images")
                    self.show_parameter_by_name("guidance_scale")
                    # Set default guidance scale
                    self.set_parameter_value("guidance_scale", 2.5)
                    # Update size choices and preserve current size if valid, otherwise default to 2048x2048 for v3 t2i
                    if current_size in new_choices:
                        self._update_option_choices("size", new_choices, current_size)
                    else:
                        self._update_option_choices("size", new_choices, "2048x2048")

                case Model.SEEDEDIT_3_0_I2I:
                    # Show single image input (required), hide images list, show guidance scale
                    self.show_parameter_by_name("image")
                    self.hide_parameter_by_name("images")
                    self.show_parameter_by_name("guidance_scale")
                    # Update tooltip for primary image parameter
                    image_param = self.get_parameter_by_name("image")
                    if image_param:
                        image_param.tooltip = "Input image (required for seededit-3.0-i2i)"
                        image_param.ui_options["display_name"] = "Input Image"
                    # Set default guidance scale
                    self.set_parameter_value("guidance_scale", 2.5)
                    # Update size choices and preserve current size if valid, otherwise default to adaptive for seededit
                    if current_size in new_choices:
                        self._update_option_choices("size", new_choices, current_size)
                    else:
                        self._update_option_choices("size", new_choices, "adaptive")

                case _:
                    msg = f"Unknown model: {model_enum}"
                    raise ValueError(msg)

        # Update validation messages when relevant parameters change
        if parameter.name in ["model", "image", "images", "size", "prompt", "seed"]:
            error_message, warning_message = self._collect_validation_errors()

            # Handle error message
            if error_message:
                validation_errors = self.get_message_by_name_or_element_id("validation_errors")
                if validation_errors:
                    validation_errors.value = error_message
                self.show_message_by_name("validation_errors")
            else:
                self.hide_message_by_name("validation_errors")

            # Handle warning message
            if warning_message:
                validation_warnings = self.get_message_by_name_or_element_id("validation_warnings")
                if validation_warnings:
                    validation_warnings.value = warning_message
                self.show_message_by_name("validation_warnings")
            else:
                self.hide_message_by_name("validation_warnings")

        return super().after_value_set(parameter, value)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def _collect_validation_errors(self) -> tuple[str, str]:
        """Collect all validation errors and warnings.

        Returns:
            Tuple of (error_message, warning_message) where each is a formatted string.
            Empty strings indicate no issues of that severity.
        """
        model = self.get_parameter_value("model")
        if model not in MODEL_CONFIG:
            return ("", "")

        config = MODEL_CONFIG[model]
        all_validations: list[ValidationMessage] = []

        # Collect all validation messages
        all_validations.extend(self._validate_image_dimensions(config))
        all_validations.extend(self._validate_image_count(config))
        all_validations.extend(self._validate_size_parameter(config))
        all_validations.extend(self._validate_prompt_length(config))
        all_validations.extend(self._validate_seed(config))

        # Separate by severity
        errors = [v.message for v in all_validations if v.severity == ValidationSeverity.ERROR]
        warnings = [v.message for v in all_validations if v.severity == ValidationSeverity.WARNING]

        error_message = "\n\n".join(errors) if errors else ""
        warning_message = "\n\n".join(warnings) if warnings else ""

        return (error_message, warning_message)

    def _validate_image_dimensions(self, config: ModelConfig) -> list[ValidationMessage]:  # noqa: C901, PLR0912
        """Validate image dimensions and aspect ratios."""
        errors = []
        model = self.get_parameter_value("model")

        # Get images based on model
        images_to_check = []
        match model:
            case Model.SEEDREAM_4_0:
                images = self.get_parameter_list_value("images") or []
                images_to_check = [(i + 1, img) for i, img in enumerate(images)]
            case Model.SEEDREAM_3_0_T2I:
                # Text-to-image model does not support image inputs
                images_to_check = []
            case Model.SEEDEDIT_3_0_I2I:
                image = self.get_parameter_value("image")
                if image:
                    images_to_check = [(None, image)]
            case _:
                msg = f"Unknown model: {model}"
                raise ValueError(msg)

        if not images_to_check:
            return errors

        for index, img in images_to_check:
            image_label = f"Image {index}" if index is not None else "Input image"

            try:
                width, height = get_image_dimensions_from_artifact(img)
            except (ValueError, TypeError) as e:
                errors.append(f"{image_label}:\n  • Failed to get image dimensions: {e}")
                self._log(f"{self.name} - {image_label}: Failed to get dimensions - {e}")
                continue
            except OSError as e:
                errors.append(f"{image_label}:\n  • Failed to read image file: {e}")
                self._log(f"{self.name} - {image_label}: Failed to read image - {e}")
                continue

            dimension_errors = []

            # Check dimensions
            if width < config.size_validation.min_dimension or height < config.size_validation.min_dimension:
                dimension_errors.append(
                    f"  • Dimensions {width}x{height} below minimum {config.size_validation.min_dimension}x{config.size_validation.min_dimension}"
                )
            if width > config.size_validation.max_dimension or height > config.size_validation.max_dimension:
                dimension_errors.append(
                    f"  • Dimensions {width}x{height} exceed maximum {config.size_validation.max_dimension}x{config.size_validation.max_dimension}"
                )

            # Check aspect ratio
            aspect_ratio = width / height if height > 0 else 0
            if (
                aspect_ratio < config.size_validation.aspect_ratio_min
                or aspect_ratio > config.size_validation.aspect_ratio_max
            ):
                dimension_errors.append(
                    f"  • Aspect ratio {aspect_ratio:.2f}:1 outside allowed range {config.size_validation.aspect_ratio_min:.2f}-{config.size_validation.aspect_ratio_max:.2f}"
                )

            if dimension_errors:
                errors.append(f"{image_label}:\n" + "\n".join(dimension_errors))

        if errors:
            message = f"{self.name} - Image validation errors:\n\n" + "\n\n".join(errors)
            return [ValidationMessage(severity=ValidationSeverity.ERROR, message=message)]
        return []

    def _validate_image_count(self, config: ModelConfig) -> list[ValidationMessage]:
        """Validate image count requirements."""
        results = []
        model = self.get_parameter_value("model")

        match model:
            case Model.SEEDREAM_4_0:
                images = self.get_parameter_list_value("images") or []
                image_count = len(images)

                # Check minimum required
                if config.min_images is not None and image_count < config.min_images:
                    message = (
                        f"{self.name} - Insufficient images: {image_count} provided but minimum is {config.min_images}"
                    )
                    results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

                # Check maximum allowed
                if config.max_images is not None and image_count > config.max_images:
                    message = (
                        f"{self.name} - Too many images: {image_count} provided but maximum is {config.max_images}"
                    )
                    results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

            case Model.SEEDREAM_3_0_T2I:
                # Text-to-image model does not support image inputs, no validation needed
                pass

            case Model.SEEDEDIT_3_0_I2I:
                image = self.get_parameter_value("image")
                has_image = image is not None

                # Check minimum required
                if config.min_images is not None and config.min_images > 0 and not has_image:
                    message = f"{self.name} - Missing required image input for {model} model"
                    results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

                # Check maximum allowed (should be exactly 1 for i2i)
                if has_image and config.max_images is not None and config.max_images < 1:
                    message = f"{self.name} - {model} does not support image inputs"
                    results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

            case _:
                msg = f"Unknown model: {model}"
                raise ValueError(msg)

        return results

    def _validate_size_parameter(self, config: ModelConfig) -> list[ValidationMessage]:
        """Validate size parameter format and values."""
        results = []
        size = self.get_parameter_value("size")
        if not size:
            return results

        # Special case for adaptive
        if size == "adaptive":
            return results

        # Check shorthand
        if size in ["1K", "2K", "4K"]:
            if not config.size_validation.allows_shorthand:
                message = f"{self.name} - Size parameter: Model does not support shorthand sizes like '{size}'. Use WIDTHxHEIGHT format (e.g., '2048x2048')"
                results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))
            return results

        # Parse WIDTHxHEIGHT format
        match = re.match(r"^(\d+)x(\d+)$", size)
        if not match:
            message = f"{self.name} - Size parameter: Invalid format '{size}'. Expected WIDTHxHEIGHT (e.g., '1024x1024') or shorthand ('1K', '2K', '4K')"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))
            return results

        width = int(match.group(1))
        height = int(match.group(2))

        # Check dimensions
        if width < config.size_validation.min_dimension or height < config.size_validation.min_dimension:
            message = f"{self.name} - Size parameter: Dimensions {width}x{height} below minimum {config.size_validation.min_dimension}x{config.size_validation.min_dimension}"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

        if width > config.size_validation.max_dimension or height > config.size_validation.max_dimension:
            message = f"{self.name} - Size parameter: Dimensions {width}x{height} exceed maximum {config.size_validation.max_dimension}x{config.size_validation.max_dimension}"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

        # Check aspect ratio
        aspect_ratio = width / height if height > 0 else 0
        if (
            aspect_ratio < config.size_validation.aspect_ratio_min
            or aspect_ratio > config.size_validation.aspect_ratio_max
        ):
            message = f"{self.name} - Size parameter: Aspect ratio {aspect_ratio:.2f}:1 outside allowed range {config.size_validation.aspect_ratio_min:.2f}-{config.size_validation.aspect_ratio_max:.2f}"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

        return results

    def _validate_prompt_length(self, config: ModelConfig) -> list[ValidationMessage]:
        """Validate prompt length against token limit."""
        results = []
        prompt = self.get_parameter_value("prompt")
        if not prompt:
            return results

        # Rough approximation: 1 token ≈ 4 characters
        estimated_tokens = len(prompt) // 4

        # Error: exceeds maximum
        if estimated_tokens > config.prompt_max_tokens:
            message = f"{self.name} - Prompt: Estimated {estimated_tokens} tokens exceeds maximum {config.prompt_max_tokens} tokens (prompt length: {len(prompt)} characters)"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))
        # Warning: approaching limit (80-100%)
        elif estimated_tokens >= int(config.prompt_max_tokens * 0.8):
            percentage = int((estimated_tokens / config.prompt_max_tokens) * 100)
            message = f"{self.name} - Prompt: Estimated {estimated_tokens} tokens is approaching the maximum {config.prompt_max_tokens} tokens ({percentage}% of limit, prompt length: {len(prompt)} characters)"
            results.append(ValidationMessage(severity=ValidationSeverity.WARNING, message=message))

        return results

    def _validate_seed(self, config: ModelConfig) -> list[ValidationMessage]:
        """Validate seed value range."""
        results = []
        seed = self.get_parameter_value("seed")
        if seed is None:
            return results

        min_seed, max_seed = config.seed_range
        if seed < min_seed or seed > max_seed:
            message = f"{self.name} - Seed: Value {seed} outside allowed range {min_seed} to {max_seed}"
            results.append(ValidationMessage(severity=ValidationSeverity.ERROR, message=message))

        return results

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before running the node.

        Only blocks execution on errors, not warnings.
        """
        error_message, _warning_message = self._collect_validation_errors()
        if error_message:
            return [ValueError(error_message)]
        return None

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
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

        try:
            response = self._submit_request(params, headers)
            if response:
                self._handle_response(response)
            else:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No response received from API. Cannot proceed with generation.",
                )
        except RuntimeError as e:
            # HTTP error or other runtime error during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)

    def _get_parameters(self) -> dict[str, Any]:
        model = self.get_parameter_value("model")
        if not model:
            msg = f"{self.name} - Model parameter is required"
            raise ValueError(msg)

        prompt = self.get_parameter_value("prompt")
        if not prompt:
            msg = f"{self.name} - Prompt parameter is required"
            raise ValueError(msg)

        size = self.get_parameter_value("size")
        if not size:
            msg = f"{self.name} - Size parameter is required"
            raise ValueError(msg)

        seed = self.get_parameter_value("seed")
        if seed is None:
            msg = f"{self.name} - Seed parameter is required"
            raise ValueError(msg)

        guidance_scale = self.get_parameter_value("guidance_scale")
        if guidance_scale is None:
            msg = f"{self.name} - Guidance scale parameter is required"
            raise ValueError(msg)

        params = {
            "model": model,
            "prompt": prompt,
            "image": self.get_parameter_value("image"),
            "size": size,
            "seed": seed,
            "guidance_scale": guidance_scale,
            "watermark": False,
        }

        # Get image list for seedream-4.0
        if params["model"] == Model.SEEDREAM_4_0:
            images = self.get_parameter_list_value("images")
            params["images"] = images if images is not None else []

        return params

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any] | None:
        payload = self._build_payload(params)
        # Map friendly model name to API model ID
        model = params["model"]
        api_model_id = MODEL_CONFIG[model].api_id if model in MODEL_CONFIG else model
        proxy_url = urljoin(self._proxy_base, api_model_id)

        self._log(f"Submitting request to Griptape model proxy with model: {params['model']}")
        self._log_request(payload)

        try:
            response = requests.post(proxy_url, json=payload, headers=headers, timeout=None)  # noqa: S113
        except requests.exceptions.ConnectionError as e:
            self._log(f"{self.name} - Connection error: {e}")
            msg = f"{self.name} - Failed to connect to Griptape model proxy: {e}"
            raise RuntimeError(msg) from e
        except requests.exceptions.Timeout as e:
            self._log(f"{self.name} - Request timeout: {e}")
            msg = f"{self.name} - Request to Griptape model proxy timed out: {e}"
            raise RuntimeError(msg) from e
        except requests.exceptions.RequestException as e:
            self._log(f"{self.name} - Request error: {e}")
            msg = f"{self.name} - Failed to submit request to Griptape model proxy: {e}"
            raise RuntimeError(msg) from e

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self._log(f"{self.name} - HTTP error: {e.response.status_code} - {e.response.text}")
            # Try to parse error response body
            try:
                error_json = e.response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                msg = f"{self.name} - API error {e.response.status_code}: {e.response.text}"
                raise RuntimeError(msg) from e

            error_details = self._extract_error_details(error_json)
            msg = f"{self.name} - {error_details}"
            raise RuntimeError(msg) from e

        try:
            response_json = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as e:
            self._log(f"{self.name} - Failed to parse response JSON: {e}")
            msg = f"{self.name} - Invalid JSON response from API: {e}"
            raise RuntimeError(msg) from e

        self._log("Request submitted successfully")
        return response_json

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        model = params["model"]
        # Map friendly model name to API model ID
        api_model_id = MODEL_CONFIG[model].api_id if model in MODEL_CONFIG else model
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
        match model:
            case Model.SEEDREAM_4_0:
                # Add multiple images if provided for v4
                images = params.get("images", [])
                if images:
                    image_array = []
                    for img in images:
                        image_data = self._process_input_image(img)
                        if image_data:
                            image_array.append(image_data)
                    if image_array:
                        payload["image"] = image_array

            case Model.SEEDREAM_3_0_T2I:
                # Add guidance scale for v3 t2i
                payload["guidance_scale"] = params["guidance_scale"]

            case Model.SEEDEDIT_3_0_I2I:
                # Add guidance scale and required image for seededit
                payload["guidance_scale"] = params["guidance_scale"]
                image_data = self._process_input_image(params["image"])
                if image_data:
                    payload["image"] = image_data

            case _:
                msg = f"Unknown model: {model}"
                raise ValueError(msg)

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
        image_bytes = self._download_bytes_from_url(url)
        if not image_bytes:
            self._log(f"{self.name} - Failed to download image from URL: {url}")
            return None

        b64_string = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64_string}"

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
            self._set_status_results(
                was_successful=False, result_details="Generation completed but no image data was found in the response."
            )
            return

        # Take first image from response
        image_data = data[0]

        # Always using URL format
        image_url = image_data.get("url")
        if image_url:
            self._save_image_from_url(image_url, generation_id)
        else:
            self._log("No image URL in response")
            self.parameter_output_values["image_url"] = None
            self._set_status_results(
                was_successful=False, result_details="Generation completed but no image URL was found in the response."
            )

    def _save_image_from_url(self, image_url: str, generation_id: str | None = None) -> None:
        self._log("Downloading image from URL")
        image_bytes = self._download_bytes_from_url(image_url)

        if not image_bytes:
            self._log(f"{self.name} - Could not download image bytes from provider URL")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details="Image generated successfully. Using provider URL (could not download image bytes).",
            )
            return

        filename = f"seedream_image_{generation_id}.jpg" if generation_id else f"seedream_image_{int(time.time())}.jpg"

        try:
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(image_bytes, filename)
        except (OSError, PermissionError) as e:
            self._log(f"{self.name} - Failed to save image to static storage: {e}")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image generated successfully. Using provider URL (could not save to static storage: {e}).",
            )
            return
        except (ValueError, TypeError) as e:
            self._log(f"{self.name} - Invalid parameters for static file save: {e}")
            self.parameter_output_values["image_url"] = ImageUrlArtifact(value=image_url)
            self._set_status_results(
                was_successful=True,
                result_details=f"Image generated successfully. Using provider URL (failed to save: {e}).",
            )
            return

        self.parameter_output_values["image_url"] = ImageUrlArtifact(value=saved_url, name=filename)
        self._log(f"Saved image to static storage as {filename}")
        self._set_status_results(
            was_successful=True, result_details=f"Image generated successfully and saved as {filename}."
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

        # Final fallback
        return f"Generation failed.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return _json.loads(provider_response)
            except (ValueError, _json.JSONDecodeError):
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
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except (requests.exceptions.RequestException, OSError):
            return None
        else:
            return resp.content
