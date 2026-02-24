from __future__ import annotations

import base64
import json
import logging
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingImageToVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
DEFAULT_DURATION_5S = 5
MAX_MULTI_PROMPT_COUNT = 6
V3_MODEL_ID = "kling-v3"


class KlingImageToVideoGeneration(GriptapeProxyNode):
    """Generate a video from an image using Kling AI models via Griptape Cloud model proxy.

    Inputs:
        - image (ImageArtifact|ImageUrlArtifact|str): Start frame image (required)
        - image_tail (ImageArtifact|ImageUrlArtifact|str): End frame image (optional, v2.1+ pro mode only)
        - model_name (str): Model to use (default: Kling v2.6)
        - multi_shot (bool): Enable multi-shot mode (Kling v3.0 only)
        - shot_type (str): Multi-shot type (customize/intelligence, Kling v3.0 only when multi_shot=true)
        - prompt (str): Text prompt for video generation (max 2500 chars)
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
        "Kling v3.0": "kling-v3",
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
        "kling-v3": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "supports_sound": False,
            "supports_tail_frame": False,
            "supports_multi_shot": True,
        },
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
                default_value="Kling v3.0",
                tooltip="Model Name for generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "Kling v3.0",
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
            ParameterBool(
                name="multi_shot",
                default_value=False,
                tooltip="Enable multi-shot mode (Kling v3.0 only).",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "multi shot", "hide": True},
            )
        )
        self.add_parameter(
            ParameterString(
                name="shot_type",
                default_value="customize",
                tooltip="Multi-shot type: customize uses per-shot prompts, intelligence auto-generates shots from prompt.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["customize", "intelligence"])},
                ui_options={"display_name": "shot type", "hide": True},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Positive text prompt (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe the desired video content..."},
            )
        )
        with ParameterGroup(name="Multi-Shot Settings") as multi_shot_settings_group:
            ParameterInt(
                name="shot_count",
                default_value=1,
                tooltip="Number of shots (1-6) for customize shot type.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[1, 2, 3, 4, 5, 6])},
                ui_options={"display_name": "shot count", "hide": True},
            )
        self.add_node_element(multi_shot_settings_group)

        for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
            with ParameterGroup(name=f"Shot {shot_index}") as shot_group:
                ParameterString(
                    name=f"shot_{shot_index}_prompt",
                    tooltip=f"Prompt for shot {shot_index}",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    multiline=True,
                    placeholder_text=f"Describe shot {shot_index}...",
                    ui_options={"display_name": f"shot {shot_index} prompt", "hide": True},
                )
                ParameterString(
                    name=f"shot_{shot_index}_duration",
                    default_value="1",
                    tooltip=f"Duration for shot {shot_index} as number-as-string.",
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    ui_options={"display_name": f"shot {shot_index} duration", "hide": True},
                )
            self.add_node_element(shot_group)

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
        self._update_parameter_visibility_for_model(self.get_parameter_value("model_name") or "Kling v3.0")
        self._update_multi_shot_parameter_visibility()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model_name":
            self._update_parameter_visibility_for_model(value)
            self._update_multi_shot_parameter_visibility()
        elif parameter.name in {"multi_shot", "shot_type", "shot_count"}:
            self._update_multi_shot_parameter_visibility()

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

        self._apply_generation_settings_visibility(model_id)

        if model_id == V3_MODEL_ID:
            self.show_parameter_by_name("multi_shot")
        else:
            self._hide_multi_shot_inputs()
            self.show_parameter_by_name("prompt")

    def _apply_generation_settings_visibility(self, model_id: str) -> None:
        """Apply mode/duration/sound visibility for selected model."""
        if model_id == "kling-v1":
            self.show_parameter_by_name("mode")
            self.hide_parameter_by_name(["duration", "sound"])
            if self.get_parameter_value("duration") != DEFAULT_DURATION_5S:
                self.set_parameter_value("duration", DEFAULT_DURATION_5S)
            return

        if model_id in {"kling-v1-5", "kling-v2-5-turbo"}:
            self.hide_parameter_by_name(["mode", "sound"])
            self.show_parameter_by_name("duration")
            if self.get_parameter_value("mode") != "pro":
                self.set_parameter_value("mode", "pro")
            return

        if model_id == "kling-v2-6":
            self.hide_parameter_by_name("mode")
            self.show_parameter_by_name(["duration", "sound"])
            if self.get_parameter_value("mode") != "pro":
                self.set_parameter_value("mode", "pro")
            if self.get_parameter_value("duration") not in [5, 10]:
                self.set_parameter_value("duration", 5)
            return

        self.show_parameter_by_name(["mode", "duration"])
        self.hide_parameter_by_name("sound")

    def _hide_multi_shot_inputs(self) -> None:
        """Hide multi-shot-specific UI inputs."""
        self.hide_parameter_by_name("multi_shot")
        self.hide_parameter_by_name("shot_type")
        self.hide_parameter_by_name("shot_count")
        for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
            self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])

    def _update_multi_shot_parameter_visibility(self) -> None:
        """Toggle prompt and shot inputs for v3 multi-shot configurations."""
        model_name = self.get_parameter_value("model_name") or "Kling v3.0"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        if model_id != V3_MODEL_ID:
            return

        is_multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"
        raw_shot_count = self.get_parameter_value("shot_count") or 1
        try:
            shot_count = int(raw_shot_count)
        except (TypeError, ValueError):
            shot_count = 1
        shot_count = max(1, min(MAX_MULTI_PROMPT_COUNT, shot_count))

        if not is_multi_shot:
            self.hide_parameter_by_name("shot_type")
            self.hide_parameter_by_name("shot_count")
            self.show_parameter_by_name("prompt")
            for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            return

        self.show_parameter_by_name("shot_type")
        if shot_type == "intelligence":
            self.show_parameter_by_name("prompt")
            self.hide_parameter_by_name("shot_count")
            for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            return

        # customize
        self.hide_parameter_by_name("prompt")
        self.show_parameter_by_name("shot_count")
        for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
            if shot_index <= shot_count:
                self.show_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            else:
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])

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

        self._add_prompt_fields(payload, model_id, prompt)

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

    def _add_prompt_fields(self, payload: dict[str, Any], model_id: str, prompt: str) -> None:
        """Attach prompt or multi_prompt fields based on multi-shot mode."""
        multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"
        shot_count = self.get_parameter_value("shot_count") or 1
        if model_id == V3_MODEL_ID:
            payload["multi_shot"] = multi_shot
            if multi_shot:
                payload["shot_type"] = shot_type
                if shot_type == "customize":
                    payload["prompt"] = ""
                    payload["multi_prompt"] = self._build_customize_multi_prompt_payload(shot_count)
                elif prompt:
                    payload["prompt"] = prompt.strip()
            elif prompt:
                payload["prompt"] = prompt.strip()
            return

        if prompt:
            payload["prompt"] = prompt.strip()

    def _build_customize_multi_prompt_payload(self, shot_count: Any) -> list[dict[str, Any]]:
        """Build multi_prompt payload from shot input parameters."""
        try:
            shot_count_int = int(shot_count)
        except (TypeError, ValueError):
            shot_count_int = 1
        shot_count_int = max(1, min(MAX_MULTI_PROMPT_COUNT, shot_count_int))

        return [
            {
                "index": shot_index,
                "prompt": (self.get_parameter_value(f"shot_{shot_index}_prompt") or "").strip(),
                "duration": str(self.get_parameter_value(f"shot_{shot_index}_duration") or "").strip(),
            }
            for shot_index in range(1, shot_count_int + 1)
        ]

    def _validate_customize_multi_shot(self, exceptions: list[Exception], shot_count: Any, duration: Any) -> None:  # noqa: C901
        """Validate customize multi-shot inputs."""
        try:
            shot_count_int = int(shot_count)
        except (TypeError, ValueError):
            exceptions.append(
                ValueError(f"{self.name} shot_count must be an integer between 1 and {MAX_MULTI_PROMPT_COUNT}.")
            )
            shot_count_int = 1

        if not (1 <= shot_count_int <= MAX_MULTI_PROMPT_COUNT):
            exceptions.append(
                ValueError(
                    f"{self.name} shot_count must be between 1 and {MAX_MULTI_PROMPT_COUNT} (got {shot_count_int})."
                )
            )
        shot_count_int = max(1, min(MAX_MULTI_PROMPT_COUNT, shot_count_int))

        total_duration = Decimal(0)
        requested_duration = Decimal(str(duration))
        for shot_index in range(1, shot_count_int + 1):
            component_prompt = (self.get_parameter_value(f"shot_{shot_index}_prompt") or "").strip()
            component_duration = self.get_parameter_value(f"shot_{shot_index}_duration")

            if not component_prompt:
                exceptions.append(ValueError(f"{self.name} shot {shot_index} prompt must be a non-empty string."))
            elif len(component_prompt) > MAX_PROMPT_LENGTH:
                exceptions.append(
                    ValueError(
                        f"{self.name} shot {shot_index} prompt exceeds {MAX_PROMPT_LENGTH} characters "
                        f"(got: {len(component_prompt)} characters)."
                    )
                )

            if not isinstance(component_duration, str):
                exceptions.append(ValueError(f"{self.name} shot {shot_index} duration must be a string number."))
                continue

            try:
                component_duration_decimal = Decimal(component_duration)
            except InvalidOperation:
                exceptions.append(
                    ValueError(
                        f"{self.name} shot {shot_index} has invalid duration '{component_duration}'. "
                        "Expected a number-as-string."
                    )
                )
                continue

            if component_duration_decimal < 1:
                exceptions.append(
                    ValueError(f"{self.name} shot {shot_index} duration must be at least 1 (got {component_duration}).")
                )
            if component_duration_decimal > requested_duration:
                exceptions.append(
                    ValueError(
                        f"{self.name} shot {shot_index} duration cannot exceed requested duration "
                        f"{duration} (got {component_duration})."
                    )
                )
            total_duration += component_duration_decimal

        if total_duration != requested_duration:
            exceptions.append(
                ValueError(f"{self.name} multi-shot durations must sum to {duration} (got {total_duration}).")
            )

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

        try:
            image_bytes = await File(image_url).aread_bytes()
        except FileLoadError as e:
            logger.debug("%s failed to load image from %s: %s", self.name, image_url, e)
            return None

        return base64.b64encode(image_bytes).decode("utf-8")

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
        try:
            logger.info("%s downloading video from provider URL", self.name)
            video_bytes = await self._download_bytes_from_url(download_url)
        except Exception as e:
            logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"kling_image_to_video_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("%s saved video to static storage as %s", self.name, filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except (OSError, PermissionError) as e:
                logger.warning("%s failed to save to static storage: %s, using provider URL", self.name, e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
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

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: C901, PLR0912
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        # Get parameter values
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        image = self.get_parameter_value("image")
        image_tail = self.get_parameter_value("image_tail")
        prompt = self.get_parameter_value("prompt") or ""
        multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"
        shot_count = self.get_parameter_value("shot_count") or 1
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
        requires_prompt = model_id != V3_MODEL_ID or (not multi_shot) or shot_type == "intelligence"
        if requires_prompt and not prompt.strip():
            exceptions.append(ValueError(f"{self.name} requires a prompt to generate video."))

        if requires_prompt and len(prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(prompt)} characters)."
                )
            )

        if model_id == V3_MODEL_ID and multi_shot:
            if shot_type not in {"customize", "intelligence"}:
                exceptions.append(ValueError(f"{self.name} shot_type must be 'customize' or 'intelligence'."))

            if shot_type == "customize":
                self._validate_customize_multi_shot(exceptions, shot_count, duration)

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
