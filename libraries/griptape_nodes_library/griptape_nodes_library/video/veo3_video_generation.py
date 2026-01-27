from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import os
from contextlib import suppress
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes.utils.artifact_normalization import normalize_artifact_list
from griptape_nodes.utils.url_utils import is_url_or_path

logger = logging.getLogger("griptape_nodes")

__all__ = ["Veo3VideoGeneration"]

# Model mapping from human-friendly names to API model IDs
MODEL_MAPPING = {
    "Veo 3.1": "veo-3.1-generate-preview",
    "Veo 3.1 Fast": "veo-3.1-fast-generate-preview",
    "Veo 3.0": "veo-3.0-generate-001",
    "Veo 3.0 Fast": "veo-3.0-fast-generate-001",
}


class Veo3VideoGeneration(SuccessFailureNode):
    """Generate a video using Google's Veo3 model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Provider model (default: Veo 3.1, options: Veo 3.1, Veo 3.1 Fast, Veo 3.0, Veo 3.0 Fast)
        - negative_prompt (str): Negative prompt to avoid certain content
        - image (ImageArtifact|ImageUrlArtifact|str): Optional start frame image (supported by all models)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image (only Veo 3.1 and Veo 3.1 Fast)
        - reference_images (list[ImageArtifact]|list[ImageUrlArtifact]|list[str]): Optional reference images (only Veo 3.1, max 3 for asset, max 1 for style)
        - reference_type (str): Reference type (default: asset, options: asset, style)
        - aspect_ratio (str): Output aspect ratio (default: 16:9, options: 16:9, 9:16)
        - resolution (str): Output resolution (default: 720p, options: 720p, 1080p)
        - duration_seconds (str): Video duration in seconds (default: 6, options: 4, 6, 8; must be 8 when referenceImages provided)
        - person_generation (str): Person generation policy (default: allow_adult, options: allow_all, allow_adult, dont_allow)
        - generate_audio (bool): Generate audio for the video (default: True, supported by all veo3* models)
        - randomize_seed (bool): If true, randomize the seed on each run (default: False)
        - seed (int): Random seed for reproducible results (default: 42)
        - sample_count (int): Number of videos to generate (default: 1, range: 1-4)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL(s) - up to 4 video outputs based on sample_count
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value="Veo 3.1",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                },
                traits={
                    Options(
                        choices=[
                            "Veo 3.1",
                            "Veo 3.1 Fast",
                            "Veo 3.0",
                            "Veo 3.0 Fast",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video",
                multiline=True,
                placeholder_text="Describe the video...",
                allow_output=False,
                ui_options={
                    "display_name": "prompt",
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="negative_prompt",
                default_value="",
                tooltip="Negative prompt to avoid certain content",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Content to avoid...",
                ui_options={
                    "display_name": "negative prompt",
                },
            )
        )

        # Image parameters
        self.add_parameter(
            ParameterImage(
                name="start_frame",
                default_value=None,
                tooltip="Optional start frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "start frame"},
            )
        )

        self.add_parameter(
            ParameterImage(
                name="last_frame",
                default_value=None,
                tooltip="Optional last frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "last frame"},
            )
        )

        # Reference images (up to 3)
        self.add_parameter(
            ParameterList(
                name="reference_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                    "list[str]",
                ],
                default_value=[],
                tooltip="Optional reference images for style and content (max 3 for asset, max 1 for style)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "reference images"},
            )
        )

        with ParameterGroup(name="Generation Settings") as video_generation_settings_group:
            # Reference type for reference images
            ParameterString(
                name="reference_type",
                default_value="asset",
                tooltip="Type of reference: 'asset' preserves objects/characters (max 3), 'style' preserves artistic style (max 1)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["asset", "style"])},
            )

            # Aspect ratio selection
            ParameterString(
                name="aspect_ratio",
                default_value="16:9",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16"])},
            )

            # Resolution selection
            ParameterString(
                name="resolution",
                default_value="720p",
                tooltip="Output resolution (1080p only supports 8 second duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "1080p"])},
            )

            # Duration in seconds
            ParameterString(
                name="duration_seconds",
                default_value="6",
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["4", "6", "8"])},
            )

            # Person generation policy
            ParameterString(
                name="person_generation",
                default_value="allow_adult",
                tooltip="Person generation policy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["allow_all", "allow_adult", "dont_allow"])},
            )

            # Generate audio option
            ParameterBool(
                name="generate_audio",
                default_value=True,
                tooltip="Generate audio for the video (supported by all veo3* models)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "generate audio"},
            )

            # Initialize SeedParameter component (adds randomize_seed and seed parameters)
            self._seed_parameter = SeedParameter(self)
            self._seed_parameter.add_input_parameters(inside_param_group=True)

            # Sample count (number of videos to generate)
            ParameterInt(
                name="sample_count",
                default_value=1,
                tooltip="Number of videos to generate (1-4)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "sample count"},
                traits={Slider(min_val=1, max_val=4)},
            )

        self.add_node_element(video_generation_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        # Create video output parameters (up to 4)
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            self.add_parameter(
                ParameterVideo(
                    name=param_name,
                    tooltip=f"Saved video {i} as URL artifact for downstream display",
                    allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                    settable=False,
                    ui_options={"pulse_on_run": True, "hide": i > 1},
                )
            )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        self._initialize_parameter_visibility()

    def _get_api_model_id(self, friendly_name: str) -> str:
        """Map friendly model name to API model ID."""
        return MODEL_MAPPING.get(friendly_name, friendly_name)

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model_id") or "Veo 3.1"
        self._update_parameter_visibility_for_model(default_model)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        if parameter.name == "model_id":
            self._update_parameter_visibility_for_model(value)
        elif parameter.name == "resolution" and value == "1080p":
            # 1080p only supports 8 second duration
            current_duration = self.get_parameter_value("duration_seconds")
            if current_duration != "8":
                logger.warning("%s: 1080p resolution only supports 8 second duration", self.name)
        elif parameter.name == "reference_images":
            # Normalize reference images (converts string paths to ImageUrlArtifact)
            if isinstance(value, list):
                updated_list = normalize_artifact_list(value, ImageUrlArtifact, accepted_types=(ImageArtifact,))
                if updated_list != value:
                    self.set_parameter_value("reference_images", updated_list)
                    value = updated_list
            self._handle_reference_images_change(value)

        return super().after_value_set(parameter, value)

    def _update_parameter_visibility_for_model(self, model_id: str) -> None:
        """Update parameter visibility based on selected model."""
        # Map friendly name to API model ID for comparison
        api_model_id = self._get_api_model_id(model_id)

        # last_frame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if api_model_id in ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"]:
            self.show_parameter_by_name("last_frame")
        else:
            self.hide_parameter_by_name("last_frame")

        # reference_images and reference_type are only supported by veo-3.1-generate-preview
        if api_model_id == "veo-3.1-generate-preview":
            self.show_parameter_by_name("reference_images")
            self.show_parameter_by_name("reference_type")
        else:
            self.hide_parameter_by_name("reference_images")
            self.hide_parameter_by_name("reference_type")

    def _handle_reference_images_change(self, reference_images: Any) -> None:
        """Handle reference images changes - enforce duration=8 when reference images are provided."""
        has_reference_images = False
        if isinstance(reference_images, list):
            has_reference_images = len(reference_images) > 0
        elif reference_images is not None:
            has_reference_images = True

        if has_reference_images:
            # When reference images are provided, duration must be 8 seconds
            current_duration = self.get_parameter_value("duration_seconds")
            if current_duration != "8":
                logger.warning(
                    "%s: Setting duration to 8 seconds (required when reference images are provided)", self.name
                )
                self.set_parameter_value("duration_seconds", "8")

    def _show_video_output_parameters(self, count: int) -> None:
        """Show/hide video output parameters based on how many videos were generated.

        Args:
            count: Number of videos generated (1-4)
        """
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            if i <= count:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def aprocess(self) -> None:
        """Main async processing entry point."""
        await self._process()

    async def _process(self) -> None:
        """Core processing logic with three phases: submit, poll, fetch."""
        # Phase 0: Clear execution status
        self._clear_execution_status()

        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        # Phase 0.5: Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Get parameters
        params = self._get_parameters()

        # Validate model-specific parameter support
        try:
            self._validate_model_parameters(params)
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Phase 1: Submit request to get generation_id
        try:
            generation_id = await self._submit_request(params, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API",
                )
                return
        except RuntimeError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Phase 2 & 3: Poll for completion and fetch result
        await self._poll_and_fetch(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        generate_audio = self.get_parameter_value("generate_audio")
        if generate_audio is None:
            generate_audio = True

        sample_count = self.get_parameter_value("sample_count")
        if sample_count is None:
            sample_count = 1

        # Normalize reference images (handles cases where values come from connections)
        reference_images = self.get_parameter_value("reference_images") or []
        normalized_reference_images = (
            normalize_artifact_list(reference_images, ImageUrlArtifact, accepted_types=(ImageArtifact,))
            if reference_images
            else []
        )

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": self.get_parameter_value("model_id") or "Veo 3.1",
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "image": self.get_parameter_value("start_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "reference_images": normalized_reference_images,
            "reference_type": self.get_parameter_value("reference_type") or "asset",
            "aspect_ratio": self.get_parameter_value("aspect_ratio") or "16:9",
            "resolution": self.get_parameter_value("resolution") or "720p",
            "duration_seconds": self.get_parameter_value("duration_seconds") or "6",
            "person_generation": self.get_parameter_value("person_generation") or "allow_adult",
            "seed": self._seed_parameter.get_seed(),
            "generate_audio": generate_audio,
            "sample_count": sample_count,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _validate_model_parameters(self, params: dict[str, Any]) -> None:
        """Validate that parameters are supported by the selected model.

        Raises ValueError if invalid parameter combinations are detected.
        """
        model_id = params["model_id"]
        # Map friendly name to API model ID for validation
        api_model_id = self._get_api_model_id(model_id)

        # lastFrame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if params.get("last_frame") and api_model_id not in [
            "veo-3.1-generate-preview",
            "veo-3.1-fast-generate-preview",
        ]:
            msg = f"{self.name}: lastFrame parameter is only supported by Veo 3.1 and Veo 3.1 Fast models. Current model: {model_id}"
            raise ValueError(msg)

        # referenceImages are only supported by veo-3.1-generate-preview
        reference_images = params.get("reference_images", [])
        has_reference_images = reference_images and len(reference_images) > 0
        if has_reference_images:
            if api_model_id != "veo-3.1-generate-preview":
                msg = f"{self.name}: referenceImages parameter is only supported by Veo 3.1 model. Current model: {model_id}"
                raise ValueError(msg)

            # When referenceImages are provided, duration must be 8 seconds
            duration = params.get("duration_seconds", "6")
            if duration != "8":
                msg = f"{self.name}: When referenceImages are provided, duration must be 8 seconds. Current duration: {duration}"
                raise ValueError(msg)

    def _convert_image_to_base64_dict(self, image_input: Any) -> dict[str, str] | None:
        """Convert image input to base64 format required by Google's API.

        Returns dict with bytesBase64Encoded and mimeType fields, or None if conversion fails.
        """
        if not image_input:
            return None

        # Handle string inputs
        if isinstance(image_input, str):
            return self._convert_string_to_base64_dict(image_input)

        # Handle artifact objects
        return self._convert_artifact_to_base64_dict(image_input)

    def _convert_string_to_base64_dict(self, image_str: str) -> dict[str, str] | None:
        """Convert string image input to base64 dict."""
        image_str = image_str.strip()
        if not image_str:
            return None

        # Handle data URI format
        if image_str.startswith("data:image/"):
            return self._parse_data_uri(image_str)

        # Handle URL - download and convert
        if is_url_or_path(image_str):
            return self._download_url_to_base64_dict(image_str)

        # Assume raw base64 string
        return {"bytesBase64Encoded": image_str, "mimeType": "image/png"}

    def _convert_artifact_to_base64_dict(self, artifact: Any) -> dict[str, str] | None:  # noqa: C901
        """Convert artifact object to base64 dict."""
        base64_data = None
        mime_type = "image/png"

        try:
            # Try ImageUrlArtifact (.value attribute)
            if hasattr(artifact, "value"):
                url_value = getattr(artifact, "value", None)
                if isinstance(url_value, str):
                    result = self._convert_string_to_base64_dict(url_value)
                    if result:
                        return result

            # Try ImageArtifact (.base64 attribute)
            if hasattr(artifact, "base64"):
                b64_value = getattr(artifact, "base64", None)
                if isinstance(b64_value, str) and b64_value:
                    if b64_value.startswith("data:image/"):
                        result = self._parse_data_uri(b64_value)
                        if result:
                            base64_data = result["bytesBase64Encoded"]
                            mime_type = result["mimeType"]
                    else:
                        base64_data = b64_value

            # Try mime_type attribute if available
            if hasattr(artifact, "mime_type"):
                artifact_mime = getattr(artifact, "mime_type", None)
                if isinstance(artifact_mime, str) and artifact_mime.startswith("image/"):
                    mime_type = artifact_mime
        except Exception as e:
            self._log(f"Warning: failed to extract base64 from artifact: {e}")
            return None

        if not base64_data:
            return None

        return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    def _parse_data_uri(self, data_uri: str) -> dict[str, str] | None:
        """Parse data URI and extract base64 data and MIME type."""
        parts = data_uri.split(",", 1)
        if len(parts) != 2:  # noqa: PLR2004
            return None

        header = parts[0]
        base64_data = parts[1]
        mime_type = "image/png"

        if ";" in header:
            mime_part = header.split(";")[0].replace("data:", "")
            if mime_part.startswith("image/"):
                mime_type = mime_part

        return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    def _download_url_to_base64_dict(self, url: str) -> dict[str, str] | None:
        """Download image from URL and convert to base64 dict."""
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(url)
                resp.raise_for_status()

            content_type = (resp.headers.get("content-type") or "image/png").split(";")[0]
            mime_type = content_type if content_type.startswith("image/") else "image/png"
            base64_data = base64.b64encode(resp.content).decode("utf-8")
        except Exception as e:
            self._log(f"Warning: failed to download image from URL: {e}")
            return None
        else:
            return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str | None:
        """Phase 1: Submit generation request and get generation_id."""
        model_id = params["model_id"]
        # Map friendly model name to API model ID
        api_model_id = self._get_api_model_id(model_id)
        payload = self._build_payload(params)

        # Construct v2 proxy URL with API model ID
        proxy_url = urljoin(self._proxy_base, f"models/{api_model_id}")

        logger.info("%s: Submitting generation request for model: %s", self.name, model_id)

        # Log full request at debug level
        self._log_request(proxy_url, headers, payload)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    proxy_url,
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPStatusError as e:
            # Extract error details from response
            error_msg = self._extract_error_from_response(e.response)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"{self.name} request failed: {e}"
            raise RuntimeError(error_msg) from e

        # Extract generation_id
        generation_id = response_json.get("generation_id")
        if generation_id:
            self.parameter_output_values["generation_id"] = str(generation_id)
            logger.info("%s: Submitted, generation_id=%s", self.name, generation_id)
            return str(generation_id)

        logger.warning("%s: No generation_id in response", self.name)
        return None

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912
        # Build instances object with prompt
        instance: dict[str, Any] = {"prompt": params["prompt"]}

        # Add images to instance object (not parameters)
        if params["image"]:
            image_dict = self._convert_image_to_base64_dict(params["image"])
            if image_dict:
                instance["image"] = image_dict

        if params["last_frame"]:
            last_frame_dict = self._convert_image_to_base64_dict(params["last_frame"])
            if last_frame_dict:
                instance["lastFrame"] = last_frame_dict

        # Add reference images to instance object (max 3 for asset, max 1 for style)
        ref_images_input = params.get("reference_images", [])
        reference_type = params.get("reference_type", "asset")
        if ref_images_input:
            # Ensure it's a list
            if not isinstance(ref_images_input, list):
                ref_images_input = [ref_images_input]

            # Limit based on reference type
            max_refs = 1 if reference_type == "style" else 3
            reference_images = []
            for ref_image in ref_images_input[:max_refs]:
                if ref_image:
                    ref_image_dict = self._convert_image_to_base64_dict(ref_image)
                    if ref_image_dict:
                        reference_images.append({"image": ref_image_dict, "referenceType": reference_type})

            if reference_images:
                instance["referenceImages"] = reference_images

        # Build parameters object (for non-image parameters)
        parameters: dict[str, Any] = {}

        # Add negative prompt if provided
        if params["negative_prompt"]:
            parameters["negativePrompt"] = params["negative_prompt"]

        # Add aspect ratio
        if params["aspect_ratio"]:
            parameters["aspectRatio"] = params["aspect_ratio"]

        # Add resolution
        if params["resolution"]:
            parameters["resolution"] = params["resolution"]

        # Add duration (convert to integer)
        if params["duration_seconds"]:
            parameters["durationSeconds"] = int(params["duration_seconds"])

        # Add person generation
        if params["person_generation"]:
            parameters["personGeneration"] = params["person_generation"]

        # Add seed
        seed = params.get("seed")
        if seed is not None:
            parameters["seed"] = int(seed)

        # Add generateAudio if provided
        if params.get("generate_audio") is not None:
            parameters["generateAudio"] = bool(params["generate_audio"])

        # Add sampleCount if provided
        sample_count = params.get("sample_count")
        if sample_count is not None and sample_count > 0:
            parameters["sampleCount"] = int(sample_count)

        return {"instances": [instance], "parameters": parameters}

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:  # noqa: C901
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
            try:
                red = deepcopy(b)
                # Sanitize images in instances array
                instances = red.get("instances", [])
                if instances and isinstance(instances, list):
                    for instance in instances:
                        if isinstance(instance, dict):
                            # Sanitize start frame and last frame
                            for key in ["image", "lastFrame"]:
                                if key in instance and isinstance(instance[key], dict):
                                    instance[key] = self._sanitize_base64_image_dict(instance[key])
                            # Sanitize reference images
                            if "referenceImages" in instance and isinstance(instance["referenceImages"], list):
                                for ref_img in instance["referenceImages"]:
                                    if isinstance(ref_img, dict) and "image" in ref_img:
                                        ref_img["image"] = self._sanitize_base64_image_dict(ref_img["image"])
            except Exception:
                return b
            else:
                return red

        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            logger.debug(
                "%s: POST %s\nheaders=%s\nbody=%s",
                self.name,
                url,
                dbg_headers,
                _json.dumps(_sanitize_body(payload), indent=2),
            )

    def _sanitize_base64_image_dict(self, image_dict: dict[str, str]) -> dict[str, str]:
        """Sanitize base64 image dict for logging by redacting the base64 data."""
        if not isinstance(image_dict, dict):
            return image_dict
        sanitized = image_dict.copy()
        if "bytesBase64Encoded" in sanitized:
            b64_data = sanitized["bytesBase64Encoded"]
            sanitized["bytesBase64Encoded"] = f"<redacted base64 length={len(b64_data)}>"
        return sanitized

    def _sanitize_result_json(self, result_json: dict[str, Any]) -> dict[str, Any]:
        """Sanitize result JSON by redacting base64-encoded video data."""
        try:
            sanitized = deepcopy(result_json)
            response = sanitized.get("response", {})
            if isinstance(response, dict):
                videos = response.get("videos", [])
                if isinstance(videos, list):
                    for video in videos:
                        if isinstance(video, dict) and "bytesBase64Encoded" in video:
                            b64_data = video["bytesBase64Encoded"]
                            video["bytesBase64Encoded"] = f"<redacted base64 length={len(b64_data)}>"
        except Exception:
            return result_json
        else:
            return sanitized

    async def _poll_and_fetch(self, generation_id: str, headers: dict[str, str]) -> None:
        """Phase 2 & 3: Poll for completion, then fetch result."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = 120  # 10 minutes with 5s intervals
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    logger.debug(
                        "%s: Polling attempt #%s for generation %s",
                        self.name,
                        attempt + 1,
                        generation_id,
                    )

                    # Poll for status
                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    result_json = response.json()

                    # Update provider_response with latest polling data
                    self.parameter_output_values["provider_response"] = result_json

                    status = result_json.get("status", "unknown")

                    # Log status at info level
                    logger.info(
                        "%s: Generation status: %s (attempt %s/%s)", self.name, status, attempt + 1, max_attempts
                    )

                    # Log full response body at debug level
                    logger.debug(
                        "%s: Generation status response:\n%s",
                        self.name,
                        _json.dumps(result_json, indent=2),
                    )

                    if status == "COMPLETED":
                        # Fetch final result
                        await self._fetch_result(generation_id, headers, client)
                        return

                    if status in ["FAILED", "ERRORED"]:
                        logger.error("%s: Generation failed: %s", self.name, status)
                        self._set_safe_defaults()
                        error_details = self._extract_error_details(result_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

                    # Still processing (QUEUED or RUNNING)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(poll_interval)

                except httpx.HTTPStatusError as e:
                    logger.error(
                        "%s: HTTP error while polling: %s",
                        self.name,
                        e.response.status_code,
                    )
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        self._set_status_results(
                            was_successful=False,
                            result_details=f"Polling failed: HTTP {e.response.status_code}",
                        )
                        return
                except Exception as e:
                    logger.error("%s: Polling error: %s", self.name, e)
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        self._set_status_results(
                            was_successful=False,
                            result_details=f"Polling failed: {e}",
                        )
                        return

            # Timeout reached
            logger.error("%s: Polling timed out", self.name)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Generation timed out after {max_attempts * poll_interval}s",
            )

    async def _fetch_result(
        self,
        generation_id: str,
        headers: dict[str, str],
        client: httpx.AsyncClient,
    ) -> None:
        """Phase 3: Fetch final result from /result endpoint.

        The v2 API returns JSON with base64-encoded video(s) in response.videos[] array.
        """
        result_url = urljoin(self._proxy_base, f"generations/{generation_id}/result")
        logger.info("%s: Fetching final result for generation: %s", self.name, generation_id)

        # Fetch the result
        result_json = await self._fetch_result_json(result_url, headers, client)
        if result_json is None:
            return

        # Check for RAI rejection
        rai_filtered_count = result_json.get("response", {}).get("raiMediaFilteredCount", 0)
        if rai_filtered_count > 0:
            logger.warning("%s: %s video(s) filtered by RAI", self.name, rai_filtered_count)

        # Extract videos array from response
        videos_array = result_json.get("response", {}).get("videos", [])
        if not videos_array:
            logger.warning("%s: No videos in result", self.name)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no videos received",
            )
            return

        # Process all videos
        video_artifacts = self._process_videos_from_result(videos_array, generation_id)

        # Check if we got any videos
        if not video_artifacts:
            logger.warning("%s: No videos could be processed", self.name)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Failed to process any videos from result",
            )
            return

        # Set output parameters
        self._set_video_output_parameters(video_artifacts)

    async def _fetch_result_json(
        self,
        result_url: str,
        headers: dict[str, str],
        client: httpx.AsyncClient,
    ) -> dict[str, Any] | None:
        """Fetch result JSON from the API.

        Returns the JSON response or None if an error occurred.
        """
        try:
            response = await client.get(result_url, headers=headers, timeout=300)
            response.raise_for_status()
            result_json = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "%s: HTTP error fetching result: %s",
                self.name,
                e.response.status_code,
            )
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Failed to fetch result: HTTP {e.response.status_code}",
            )
            return None
        except Exception as e:
            logger.error("%s: Error fetching result: %s", self.name, e)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Failed to fetch result: {e}",
            )
            return None
        else:
            logger.info("%s: Result fetched successfully", self.name)
            logger.debug(
                "%s: Result response:\n%s",
                self.name,
                _json.dumps(self._sanitize_result_json(result_json), indent=2),
            )
            return result_json

    def _process_videos_from_result(
        self,
        videos_array: list[dict[str, Any]],
        generation_id: str,
    ) -> list[VideoUrlArtifact]:
        """Process all videos from the result array.

        Returns a list of VideoUrlArtifact objects.
        """
        video_artifacts = []
        static_files_manager = GriptapeNodes.StaticFilesManager()

        for idx, video_data in enumerate(videos_array, start=1):
            artifact = self._process_single_video(video_data, generation_id, idx, static_files_manager)
            if artifact:
                video_artifacts.append(artifact)

        return video_artifacts

    def _process_single_video(
        self,
        video_data: dict[str, Any],
        generation_id: str,
        idx: int,
        static_files_manager: Any,
    ) -> VideoUrlArtifact | None:
        """Process a single video from base64 data.

        Returns a VideoUrlArtifact or None if processing failed.
        """
        try:
            base64_data = video_data.get("bytesBase64Encoded")
            mime_type = video_data.get("mimeType", "video/mp4")

            if not base64_data:
                logger.warning("%s: Video %s missing base64 data", self.name, idx)
                return None

            # Decode base64
            video_bytes = base64.b64decode(base64_data)

            # Determine file extension from mime type
            extension = "mp4"
            if "/" in mime_type:
                extension = mime_type.split("/")[1]

            # Save to static storage
            filename = f"veo3_video_{generation_id}_{idx}.{extension}"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)

            logger.info("%s: Saved video %s as %s (%s bytes)", self.name, idx, filename, len(video_bytes))

            return VideoUrlArtifact(value=saved_url, name=filename)

        except Exception as e:
            logger.error("%s: Failed to process video %s: %s", self.name, idx, e)
            return None

    def _set_video_output_parameters(self, video_artifacts: list[VideoUrlArtifact]) -> None:
        """Set output parameters for all generated videos."""
        # Show appropriate number of output parameters
        self._show_video_output_parameters(len(video_artifacts))

        # Set individual output parameters
        for idx, artifact in enumerate(video_artifacts, start=1):
            param_name = "video_url" if idx == 1 else f"video_url_{idx}"
            self.parameter_output_values[param_name] = artifact

        # Set success status
        video_count = len(video_artifacts)
        result_message = f"Generated {video_count} video{'s' if video_count > 1 else ''} successfully"
        self._set_status_results(
            was_successful=True,
            result_details=result_message,
        )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract detailed error message from API response.

        The v2 API provides errors in status_detail field.
        """
        if not response_json:
            return f"{self.name}: Generation failed with no error details"

        # Check v2 API status_detail first (for FAILED/ERROR statuses)
        status_detail = response_json.get("status_detail")
        if status_detail:
            return f"{self.name}: Generation failed\n\n{_json.dumps(status_detail, indent=2)}"

        # Check top-level error field
        top_level_error = response_json.get("error")
        if top_level_error:
            if isinstance(top_level_error, dict):
                return f"{self.name}: {_json.dumps(top_level_error, indent=2)}"
            return f"{self.name}: {top_level_error}"

        # Final fallback
        status = self._extract_status(response_json) or "unknown"
        return f"{self.name}: Generation failed with status '{status}'"

    def _extract_error_from_response(self, response: httpx.Response) -> str:
        """Extract error message from HTTP error response."""
        try:
            error_json = response.json()
            return self._extract_error_details(error_json)
        except Exception:
            return f"{self.name}: API error: {response.status_code} - {response.text}"

    def _set_safe_defaults(self) -> None:
        """Set safe default values for all outputs on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        # Clear all video output parameters
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            self.parameter_output_values[param_name] = None

    @staticmethod
    def _extract_status(obj: dict[str, Any] | None) -> str | None:
        """Extract status from Veo3 response (only checks top-level 'status' field)."""
        if not obj or not isinstance(obj, dict):
            return None
        return obj.get("status") if isinstance(obj.get("status"), str) else None
