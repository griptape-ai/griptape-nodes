from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from contextlib import suppress
from copy import deepcopy
from time import monotonic, sleep
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["Veo3VideoGeneration"]


class Veo3VideoGeneration(SuccessFailureNode):
    """Generate a video using Google's Veo3 model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Provider model id (default: veo-3.1-generate-preview)
        - negative_prompt (str): Negative prompt to avoid certain content
        - image (ImageArtifact|ImageUrlArtifact|str): Optional start frame image (supported by all models)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image (only veo-3.1-generate-preview and veo-3.1-fast-generate-preview)
        - reference_images (list[ImageArtifact]|list[ImageUrlArtifact]|list[str]): Optional reference images (only veo-3.1-generate-preview, max 3 for asset, max 1 for style)
        - reference_type (str): Reference type (default: asset, options: asset, style)
        - aspect_ratio (str): Output aspect ratio (default: 16:9, options: 16:9, 9:16)
        - resolution (str): Output resolution (default: 720p, options: 720p, 1080p)
        - duration_seconds (str): Video duration in seconds (default: 6, options: 4, 6, 8; must be 8 when referenceImages provided)
        - person_generation (str): Person generation policy (default: allow_adult, options: allow_all, allow_adult, dont_allow)
        - generate_audio (bool): Generate audio for the video (default: True, supported by all veo3* models)
        - seed (int): Random seed for reproducible results (default: -1, -1 means don't specify a seed, 0 or above will be sent)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Google Veo3 through Griptape Cloud model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="veo-3.1-generate-preview",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "veo-3.1-generate-preview",
                            "veo-3.1-fast-generate-preview",
                            "veo-3.0-generate-001",
                            "veo-3.0-fast-generate-001",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Negative prompt to avoid certain content",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Content to avoid...",
                    "display_name": "negative prompt",
                },
            )
        )

        # Image parameters
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional start frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "start frame"},
            )
        )

        self.add_parameter(
            Parameter(
                name="last_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
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

        # Reference type for reference images
        self.add_parameter(
            Parameter(
                name="reference_type",
                input_types=["str"],
                type="str",
                default_value="asset",
                tooltip="Type of reference: 'asset' preserves objects/characters (max 3), 'style' preserves artistic style (max 1)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["asset", "style"])},
            )
        )

        # Aspect ratio selection
        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16"])},
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="720p",
                tooltip="Output resolution (1080p only supports 8 second duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "1080p"])},
            )
        )

        # Duration in seconds
        self.add_parameter(
            Parameter(
                name="duration_seconds",
                input_types=["str"],
                type="str",
                default_value="6",
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["4", "6", "8"])},
            )
        )

        # Person generation policy
        self.add_parameter(
            Parameter(
                name="person_generation",
                input_types=["str"],
                type="str",
                default_value="allow_adult",
                tooltip="Person generation policy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["allow_all", "allow_adult", "dont_allow"])},
            )
        )

        # Generate audio option
        self.add_parameter(
            Parameter(
                name="generate_audio",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Generate audio for the video (supported by all veo3* models)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "generate audio"},
            )
        )

        # Seed for reproducibility
        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int", "str"],
                type="int",
                default_value=-1,
                tooltip="Random seed for reproducible results (-1 to not specify a seed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "seed"},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

        # Set initial parameter visibility based on default model
        self._initialize_parameter_visibility()

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model_id") or "veo-3.1-generate-preview"
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
            self._handle_reference_images_change(value)

        return super().after_value_set(parameter, value)

    def _update_parameter_visibility_for_model(self, model_id: str) -> None:
        """Update parameter visibility based on selected model."""
        # last_frame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if model_id in ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"]:
            self.show_parameter_by_name("last_frame")
        else:
            self.hide_parameter_by_name("last_frame")

        # reference_images and reference_type are only supported by veo-3.1-generate-preview
        if model_id == "veo-3.1-generate-preview":
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

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Get parameters and validate API key
        params = self._get_parameters()

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Validate model-specific parameter support
        try:
            self._validate_model_parameters(params)
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Build and submit request
        try:
            generation_id = self._submit_request(params, headers)
            if not generation_id:
                self.parameter_output_values["result"] = None
                self.parameter_output_values["video_url"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        self._poll_for_result(generation_id, headers)

    def _get_parameters(self) -> dict[str, Any]:
        generate_audio = self.get_parameter_value("generate_audio")
        if generate_audio is None:
            generate_audio = True

        seed = self.get_parameter_value("seed")
        if seed is None:
            seed = -1

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": self.get_parameter_value("model_id") or "veo-3.1-generate-preview",
            "negative_prompt": self.get_parameter_value("negative_prompt") or "",
            "image": self.get_parameter_value("image"),
            "last_frame": self.get_parameter_value("last_frame"),
            "reference_images": self.get_parameter_value("reference_images") or [],
            "reference_type": self.get_parameter_value("reference_type") or "asset",
            "aspect_ratio": self.get_parameter_value("aspect_ratio") or "16:9",
            "resolution": self.get_parameter_value("resolution") or "720p",
            "duration_seconds": self.get_parameter_value("duration_seconds") or "6",
            "person_generation": self.get_parameter_value("person_generation") or "allow_adult",
            "seed": seed,
            "generate_audio": generate_audio,
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

        # lastFrame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if params.get("last_frame") and model_id not in ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"]:
            msg = f"{self.name}: lastFrame parameter is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview models. Current model: {model_id}"
            raise ValueError(msg)

        # referenceImages are only supported by veo-3.1-generate-preview
        reference_images = params.get("reference_images", [])
        has_reference_images = reference_images and len(reference_images) > 0
        if has_reference_images:
            if model_id != "veo-3.1-generate-preview":
                msg = f"{self.name}: referenceImages parameter is only supported by veo-3.1-generate-preview model. Current model: {model_id}"
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
        if image_str.startswith(("http://", "https://")):
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

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model_id']}")
        payload = self._build_payload(params)

        self._log(f"Submitting request to proxy model={params['model_id']}")
        self._log_request(post_url, headers, payload)

        try:
            with httpx.Client(timeout=60.0) as client:
                post_resp = client.post(post_url, json=payload, headers=headers)
        except Exception as e:
            self._set_safe_defaults()
            msg = f"Failed to connect to proxy API: {e}"
            raise RuntimeError(msg) from e

        if post_resp.status_code >= 400:  # noqa: PLR2004
            self._set_safe_defaults()
            self._log(
                f"Proxy POST error status={post_resp.status_code} headers={dict(post_resp.headers)} body={post_resp.text}"
            )
            try:
                error_json = post_resp.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"Proxy POST error: {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        post_json = post_resp.json()
        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response

        if generation_id:
            self._log(f"Submitted. generation_id={generation_id}")
        else:
            self._log("No generation_id returned from POST response")

        return generation_id

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

        # Add seed if >= 0 (-1 means don't specify)
        seed = params.get("seed", -1)
        if seed is not None and seed >= 0:
            parameters["seed"] = int(seed)

        # Add generateAudio if provided
        if params.get("generate_audio") is not None:
            parameters["generateAudio"] = bool(params["generate_audio"])

        return {"instances": [instance], "parameters": parameters}

    def _prepare_image_url(self, image_input: Any) -> str | None:
        """Convert image input to a usable URL, handling inlining of external URLs."""
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        return self._inline_external_url(image_url)

    def _inline_external_url(self, url: str) -> str | None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return url

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(url)
                resp.raise_for_status()

            ct = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
            if not ct.startswith("image/"):
                ct = "image/jpeg"
            b64 = base64.b64encode(resp.content).decode("utf-8")
            self._log("Image URL converted to data URI for proxy")
        except Exception as e:
            self._log(f"Warning: failed to inline image URL: {e}")
            return url
        else:
            return f"data:{ct};base64,{b64}"

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
            self._log(f"POST {url}\nheaders={dbg_headers}\nbody={_json.dumps(_sanitize_body(payload), indent=2)}")

    def _sanitize_base64_image_dict(self, image_dict: dict[str, str]) -> dict[str, str]:
        """Sanitize base64 image dict for logging by redacting the base64 data."""
        if not isinstance(image_dict, dict):
            return image_dict
        sanitized = image_dict.copy()
        if "bytesBase64Encoded" in sanitized:
            b64_data = sanitized["bytesBase64Encoded"]
            sanitized["bytesBase64Encoded"] = f"<redacted base64 length={len(b64_data)}>"
        return sanitized

    def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 600.0

        while True:
            if monotonic() - start_time > timeout_s:
                self.parameter_output_values["video_url"] = self._extract_video_url(last_json)
                self._log("Polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Video generation timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                with httpx.Client(timeout=60.0) as client:
                    get_resp = client.get(get_url, headers=headers)
                    get_resp.raise_for_status()

                    # Check if response is the video itself (application/octet-stream)
                    content_type = get_resp.headers.get("content-type", "")
                    if "application/octet-stream" in content_type:
                        self._log("Received video as application/octet-stream")
                        video_bytes = get_resp.content
                        self._handle_video_bytes_completion(video_bytes, generation_id)
                        return

                    # Otherwise, parse as JSON and continue polling
                    last_json = get_resp.json()
                # Update provider_response with latest polling data
                self.parameter_output_values["provider_response"] = last_json
            except Exception as exc:
                self._log(f"GET generation failed: {exc}")
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            with suppress(Exception):
                self._log(f"GET payload attempt #{attempt + 1}: {_json.dumps(last_json, indent=2)}")

            # Check if done
            is_done = self._is_done(last_json)
            status = self._extract_status(last_json) or "running"
            attempt += 1
            self._log(f"Polling attempt #{attempt} status={status} done={is_done}")

            # Check for explicit failure statuses
            if status.lower() in {"failed", "error"}:
                self._log(f"Generation failed with status: {status}")
                self.parameter_output_values["video_url"] = None
                error_details = self._extract_error_details(last_json)
                self._set_status_results(was_successful=False, result_details=error_details)
                return

            if is_done or status.lower() in {"succeeded", "success", "completed"}:
                self._handle_completion(last_json, generation_id)
                return

            sleep(poll_interval_s)

    def _is_done(self, obj: dict[str, Any] | None) -> bool:
        """Check if the generation is done based on the 'done' field."""
        if not isinstance(obj, dict):
            return False
        return obj.get("done", False) is True

    def _extract_rai_rejection_reason(self, obj: dict[str, Any] | None) -> str | None:
        """Extract RAI (Responsible AI) filtering/rejection reasons from the response.

        Google's API returns rejection reasons in response.generateVideoResponse.raiMediaFilteredReasons
        when content is filtered by safety systems.
        """
        if not isinstance(obj, dict):
            return None

        try:
            # Navigate to the generateVideoResponse object
            response = obj.get("response")
            generate_video_response = response.get("generateVideoResponse") if isinstance(response, dict) else None
            if not isinstance(generate_video_response, dict):
                return None

            # Check for filtered reasons and count
            filtered_count = generate_video_response.get("raiMediaFilteredCount", 0)
            filtered_reasons = generate_video_response.get("raiMediaFilteredReasons")

            # Format the rejection message if reasons exist
            if filtered_count > 0 and isinstance(filtered_reasons, list) and filtered_reasons:
                reasons_text = "\n\n".join(f"- {reason}" for reason in filtered_reasons if isinstance(reason, str))
                if reasons_text:
                    return f"{self.name}: Video generation rejected by Google's safety filters.\n\n{reasons_text}"
        except Exception as e:
            logger.warning("Failed to extract RAI rejection reason: %s", e)

        return None

    def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        # Check for RAI (Responsible AI) filtering or rejection
        rai_rejection_reason = self._extract_rai_rejection_reason(last_json)
        if rai_rejection_reason:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details=rai_rejection_reason)
            return

        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        try:
            self._log("Downloading video bytes from provider URL")
            video_bytes = self._download_bytes_from_url(extracted_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_bytes = None

        if video_bytes:
            try:
                filename = f"veo3_video_{generation_id}.mp4" if generation_id else f"veo3_video_{int(time.time())}.mp4"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved video to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                self._log(f"Failed to save to static storage: {e}, using provider URL")
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _handle_video_bytes_completion(self, video_bytes: bytes, generation_id: str | None = None) -> None:
        """Handle completion when video bytes are received directly in the response."""
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video data was received.",
            )
            return

        try:
            filename = f"veo3_video_{generation_id}.mp4" if generation_id else f"veo3_video_{int(time.time())}.mp4"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved video to static storage as {filename}")
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        except Exception as e:
            self._log(f"Failed to save video to static storage: {e}")
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"Video was generated but could not be saved to static storage: {e}",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return f"{self.name} failed with no error details provided by API."

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
        status = self._extract_status(response_json) or "unknown"
        return f"{self.name} failed with status '{status}'.\n\nFull API response:\n{response_json}"

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
            details = f"{self.name}: {error_message}"

            if error_code := provider_error.get("code"):
                details += f"\nError Code: {error_code}"
            if error_type := provider_error.get("type"):
                details += f"\nError Type: {error_type}"
            if top_level_error:
                details = f"{top_level_error}\n\n{details}"
            return details

        error_msg = str(provider_error)
        if top_level_error:
            return f"{self.name}: {top_level_error}\n\nProvider error: {error_msg}"
        return f"{self.name} failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"{self.name} failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"{self.name} failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["result"] = None
        self.parameter_output_values["status"] = "error"
        self.parameter_output_values["video_url"] = None

    @staticmethod
    def _extract_status(obj: dict[str, Any] | None) -> str | None:
        """Extract status from Veo3 response (only checks top-level 'status' field)."""
        if not obj or not isinstance(obj, dict):
            return None
        return obj.get("status") if isinstance(obj.get("status"), str) else None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        """Extract video URL from Veo3 response.

        Expected path: response.generateVideoResponse.generatedSamples[0].video_uri
        """
        if not obj or not isinstance(obj, dict):
            return None

        try:
            response = obj.get("response")
            generate_video_response = response.get("generateVideoResponse") if isinstance(response, dict) else None
            generated_samples = (
                generate_video_response.get("generatedSamples") if isinstance(generate_video_response, dict) else None
            )

            if not (isinstance(generated_samples, list) and len(generated_samples) > 0):
                return None

            first_sample = generated_samples[0]
            video_uri = first_sample.get("video_uri") if isinstance(first_sample, dict) else None

            if isinstance(video_uri, str) and video_uri.startswith("http"):
                return video_uri

        except Exception as e:
            logger.warning("Failed to extract video URL from Veo3 response: %s", e)

        return None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except Exception:  # noqa: S110
            pass

        return None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
