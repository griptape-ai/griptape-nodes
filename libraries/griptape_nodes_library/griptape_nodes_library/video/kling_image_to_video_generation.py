from __future__ import annotations

import json
import logging
from contextlib import suppress
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.events.static_file_events import (
    DownloadAndSaveRequest,
    DownloadAndSaveResultSuccess,
    LoadAsBase64DataUriRequest,
    LoadAsBase64DataUriResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingImageToVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
DEFAULT_DURATION_5S = 5


class KlingImageToVideoGeneration(GriptapeProxyNode):
    """Generate a video from an image using Kling AI models via Griptape Cloud model proxy.

    Inputs:
        - image (ImageArtifact|ImageUrlArtifact|str): Start frame image (required)
        - image_tail (ImageArtifact|ImageUrlArtifact|str): End frame image (optional, v2.1+ pro mode only)
        - prompt (str): Text prompt for video generation (max 2500 chars)
        - model_name (str): Model to use (default: Kling v2.6)
        - negative_prompt (str): Negative text prompt (max 2500 chars)
        - cfg_scale (float): Flexibility in video generation (0-1)
        - mode (str): Video generation mode (std: Standard, pro: Professional)
        - duration (int): Video length in seconds
        - sound (str): Generate native audio with the video (Kling v2.6 only)
        - static_mask (ImageArtifact|ImageUrlArtifact|str): Static mask for brush application
        - dynamic_masks (str): JSON string for dynamic brush configuration
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - video_id (str): The Kling AI video ID
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Kling v2.6": "kling-v2-6",
        "Kling v2.5 Turbo": "kling-v2-5-turbo",
        "Kling v2.1 Master": "kling-v2-1-master",
        "Kling v2.1": "kling-v2-1",
        "Kling v2 Master": "kling-v2-master",
        "Kling v1.5": "kling-v1-5",
        "Kling v1": "kling-v1",
    }

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "kling-v1": {
            "modes": ["std", "pro"],
            "durations": [5],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v1-5": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-1": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": True,  # Only with pro mode
        },
        "kling-v2-1-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
        },
        "kling-v2-5-turbo": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": True,  # Only with pro mode
        },
        "kling-v2-6": {
            "modes": ["pro"],
            "durations": [5, 10],
            "supports_sound": True,
            "supports_tail_frame": False,
        },
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model_name",
                default_value="Kling v2.6",
                tooltip="Model Name for generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "Kling v2.6",
                            "Kling v2.5 Turbo",
                            "Kling v2.1 Master",
                            "Kling v2.1",
                            "Kling v2 Master",
                            "Kling v1.5",
                            "Kling v1",
                        ]
                    )
                },
                ui_options={"display_name": "Model"},
            )
        )

        # Prompts
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Positive text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe the desired video content..."},
            )
        )
        self.add_parameter(
            ParameterString(
                name="negative_prompt",
                default_value="",
                tooltip="Negative text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        # Image Inputs
        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Start frame image (required). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Start Frame"},
            )
        )
        self.add_parameter(
            ParameterImage(
                name="image_tail",
                tooltip="End frame image (optional). Supported on kling-v2-1 and kling-v2-5-turbo with pro mode.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "End Frame"},
            )
        )

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterFloat(
                name="cfg_scale",
                default_value=0.5,
                tooltip="Flexibility (0-1). Higher value = lower flexibility, stronger prompt relevance.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode (std: Standard, pro: Professional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video length in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
            ParameterString(
                name="sound",
                default_value="off",
                tooltip="Generate native audio with the video (kling-v2-6 only)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["on", "off"])},
                ui_options={"hide": True},
            )
        self.add_node_element(gen_settings_group)

        # Masks Group
        with ParameterGroup(name="Masks") as masks_group:
            ParameterImage(
                name="static_mask",
                default_value=None,
                tooltip="Static brush application area. Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            ParameterString(
                name="dynamic_masks",
                default_value="",
                tooltip="JSON string for dynamic brush configuration list. Masks within JSON must be URL/Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Enter JSON for dynamic masks..."},
            )
        masks_group.ui_options = {"hide": True}
        self.add_node_element(masks_group)

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
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video_url",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The Kling AI video ID",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The Kling AI video ID",
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        self._update_parameter_visibility_for_model("Kling v2.6")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model_name":
            self._update_parameter_visibility_for_model(value)

    def _update_parameter_visibility_for_model(self, model_name: str) -> None:
        """Update parameter visibility based on selected model."""
        # Map user-facing name to model ID
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)

        # Show mask features for all models
        self.show_parameter_by_name(["static_mask", "dynamic_masks"])

        # Show/hide image_tail (end frame) based on model support
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})
        if capabilities.get("supports_tail_frame", False):
            self.show_parameter_by_name("image_tail")
        else:
            self.hide_parameter_by_name("image_tail")

        if model_id == "kling-v1":
            self.show_parameter_by_name("mode")
            self.hide_parameter_by_name(["duration", "sound"])
            current_duration = self.get_parameter_value("duration")
            if current_duration != DEFAULT_DURATION_5S:
                self.set_parameter_value("duration", DEFAULT_DURATION_5S)
        elif model_id in {"kling-v1-5", "kling-v2-5-turbo"}:
            self.hide_parameter_by_name(["mode", "sound"])
            self.show_parameter_by_name("duration")
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
        elif model_id == "kling-v2-6":
            self.hide_parameter_by_name("mode")
            self.show_parameter_by_name(["duration", "sound"])
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
            current_duration = self.get_parameter_value("duration")
            if current_duration not in [5, 10]:
                self.set_parameter_value("duration", 5)
        else:
            self.show_parameter_by_name(["mode", "duration"])
            self.hide_parameter_by_name("sound")

    async def aprocess(self) -> None:
        await super().aprocess()

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Appends :image2video modality to the model name.
        """
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{model_id}:image2video"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Kling API.

        Returns:
            dict: The request payload (model field excluded, handled by base class)
        """
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        image = await self._prepare_image_data_url_async(self.get_parameter_value("image"))
        image_tail = await self._prepare_image_data_url_async(self.get_parameter_value("image_tail"))
        prompt = self.get_parameter_value("prompt") or ""
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        cfg_scale = self.get_parameter_value("cfg_scale") or 0.5
        mode = self.get_parameter_value("mode") or "pro"
        duration = self.get_parameter_value("duration") or 5
        sound = self.get_parameter_value("sound") or "off"
        static_mask = await self._prepare_image_data_url_async(self.get_parameter_value("static_mask"))
        dynamic_masks = self.get_parameter_value("dynamic_masks") or ""

        payload: dict[str, Any] = {
            "model_name": model_id,
            "duration": int(duration),
            "cfg_scale": float(cfg_scale),
            "mode": mode,
        }

        # Add images
        if image:
            payload["image"] = image

        if image_tail:
            payload["image_tail"] = image_tail

        # Add prompts if provided
        if prompt:
            payload["prompt"] = prompt.strip()

        if negative_prompt:
            payload["negative_prompt"] = negative_prompt.strip()

        # Add sound parameter for v2.6
        if model_id == "kling-v2-6" and sound:
            payload["sound"] = sound

        # Add masks if provided
        if static_mask:
            payload["static_mask"] = static_mask

        if dynamic_masks:
            with suppress(json.JSONDecodeError):
                payload["dynamic_masks"] = json.loads(dynamic_masks)

        return payload

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        """Convert image input to a data URL, handling external URLs by downloading and converting."""
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # If it's already a data URL, return it
        if image_url.startswith("data:image/"):
            return image_url

        # If it's an external URL, download and convert to data URL
        if image_url.startswith(("http://", "https://")):
            return await self._inline_external_url_async(image_url)

        return image_url

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Download external image URL and convert to data URL."""
        request = LoadAsBase64DataUriRequest(artifact_or_url=url, context_name=f"{self.name}.input_image")
        result = await GriptapeNodes.ahandle_request(request)
        if isinstance(result, LoadAsBase64DataUriResultSuccess):
            logger.debug("Image URL converted to data URI for proxy")
            return result.data_uri
        return None

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the result and set output parameters.

        Expected structure: {"data": {"task_result": {"videos": [{"url": "...", "id": "..."}]}}}
        """
        data = result_json.get("data", {})
        task_result = data.get("task_result", {})
        videos = task_result.get("videos", [])

        if not videos or not isinstance(videos, list) or len(videos) == 0:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no videos found in response.",
            )
            return

        video_info = videos[0]
        download_url = video_info.get("url")
        video_id = video_info.get("id")

        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download URL found in response.",
            )
            return

        # Set kling_video_id output parameter
        if video_id:
            self.parameter_output_values["kling_video_id"] = video_id
            logger.info("Video ID: %s", video_id)

        # Download and save video
        filename = f"kling_image_to_video_{generation_id}.mp4"
        request = DownloadAndSaveRequest(
            url=download_url,
            filename=filename,
            artifact_type=VideoUrlArtifact,
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, DownloadAndSaveResultSuccess):
            self.parameter_output_values["video_url"] = result.artifact
            logger.info("%s saved video to static storage as %s", self.name, filename)
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _set_safe_defaults(self) -> None:
        """Clear output parameters on error."""
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["kling_video_id"] = ""

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: C901
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        # Get parameter values
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        image = self.get_parameter_value("image")
        image_tail = self.get_parameter_value("image_tail")
        prompt = self.get_parameter_value("prompt") or ""
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        cfg_scale = self.get_parameter_value("cfg_scale") or 0.5
        mode = self.get_parameter_value("mode") or "pro"
        duration = self.get_parameter_value("duration") or 5
        dynamic_masks = self.get_parameter_value("dynamic_masks") or ""

        # Validate at least one image is provided
        if not image and not image_tail:
            exceptions.append(
                ValueError(f"{self.name} requires at least one of 'image' (start frame) or 'image_tail' (end frame).")
            )

        # Validate prompt length
        if prompt and len(prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(prompt)} characters)."
                )
            )

        # Validate negative prompt length
        if negative_prompt and len(negative_prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} negative_prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(negative_prompt)} characters)."
                )
            )

        # Validate cfg_scale
        if not (0 <= cfg_scale <= 1):
            exceptions.append(ValueError(f"{self.name} cfg_scale must be between 0.0 and 1.0."))

        # Validate model-specific constraints
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})

        if mode not in capabilities.get("modes", ["std", "pro"]):
            valid_modes = capabilities.get("modes", [])
            exceptions.append(
                ValueError(
                    f"{self.name}: Model {model_name} does not support mode '{mode}'. "
                    f"Valid modes: {', '.join(valid_modes)}"
                )
            )

        if duration not in capabilities.get("durations", [5, 10]):
            valid_durations = capabilities.get("durations", [])
            exceptions.append(
                ValueError(
                    f"{self.name}: Model {model_name} does not support duration {duration}s. "
                    f"Valid durations: {', '.join(map(str, valid_durations))}"
                )
            )

        # Validate tail frame support
        if image_tail:
            supports_tail = capabilities.get("supports_tail_frame", False)
            if not supports_tail:
                exceptions.append(
                    ValueError(
                        f"{self.name}: Model {model_name} does not support end frame (image_tail). "
                        f"Only Kling v2.1 and Kling v2.5 Turbo with pro mode support end frames."
                    )
                )

            if supports_tail and mode != "pro":
                exceptions.append(ValueError(f"{self.name}: End frame (image_tail) requires pro mode."))

        # Validate dynamic_masks JSON if provided
        if dynamic_masks:
            try:
                json.loads(dynamic_masks)
            except json.JSONDecodeError as e:
                exceptions.append(ValueError(f"{self.name} dynamic_masks is not valid JSON: {e}"))

        return exceptions if exceptions else None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        """Convert various image input types to a URL or data URI string."""
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
        except AttributeError:
            pass

        return None
