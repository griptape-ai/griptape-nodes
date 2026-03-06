from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.widget import Widget
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingTextToVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
MAX_MULTI_PROMPT_COUNT = 6
V3_MODEL_ID = "kling-v3"
DEFAULT_MULTI_SHOTS = [{"name": "Shot1", "duration": 5, "description": ""}]


class KlingTextToVideoGeneration(GriptapeProxyNode):
    """Generate a video from text using Kling AI models via Griptape Cloud model proxy.

    Inputs:
        - model_name (str): Model to use (default: Kling v2.6)
        - multi_shot (bool): Enable multi-shot mode (Kling v3.0 only)
        - shot_type (str): Multi-shot type (customize/intelligence, Kling v3.0 only when multi_shot=true)
        - prompt (str): Text prompt for video generation (max 2500 chars)
        - negative_prompt (str): Negative text prompt (max 2500 chars)
        - cfg_scale (float): Flexibility in video generation (0-1)
        - mode (str): Video generation mode (std: Standard, pro: Professional)
        - aspect_ratio (str): Aspect ratio of the generated video frame
        - duration (int): Video length in seconds
        - sound (str): Generate native audio with the video (Kling v2.6 only)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - kling_video_id (str): The Kling AI video ID
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Kling v3.0": "kling-v3",
        "Kling v2.6": "kling-v2-6",
        "Kling v2.5 Turbo": "kling-v2-5-turbo",
        "Kling v2.1 Master": "kling-v2-1-master",
        "Kling v2 Master": "kling-v2-master",
        "Kling v1.6": "kling-v1-6",
    }

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "kling-v3": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "supports_sound": False,
            "supports_multi_shot": True,
        },
        "kling-v1-6": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "supports_sound": False,
        },
        "kling-v2-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "supports_sound": False,
        },
        "kling-v2-1-master": {
            "modes": ["std", "pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "supports_sound": False,
        },
        "kling-v2-5-turbo": {
            "modes": ["pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9"],
            "supports_sound": False,
        },
        "kling-v2-6": {
            "modes": ["pro"],
            "durations": [5, 10],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "supports_sound": True,
        },
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            ParameterString(
                name="model_name",
                default_value="Kling v3.0",
                tooltip="Model Name",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "Kling v3.0",
                            "Kling v2.6",
                            "Kling v2.5 Turbo",
                            "Kling v2.1 Master",
                            "Kling v2 Master",
                            "Kling v1.6",
                        ]
                    )
                },
            )
        )

        # INPUTS / PROPERTIES
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
                tooltip="Text prompt for video generation (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video you want...",
                    "display_name": "prompt",
                },
            )
        )
        self.add_parameter(
            Parameter(
                name="shots",
                input_types=["list"],
                type="list",
                output_type="list",
                default_value=DEFAULT_MULTI_SHOTS,
                tooltip="Shot sequence for Kling v3 multi-shot customize mode.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Widget(name="KlingMultiShotEditor", library="Griptape Nodes Library")},
                ui_options={"display_name": "shot sequence", "hide": True},
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

        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterFloat(
                name="cfg_scale",
                default_value=0.5,
                tooltip="Flexibility in video generation (0-1). Higher value = lower flexibility, stronger prompt relevance.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            ParameterString(
                name="mode",
                default_value="std",
                tooltip="Video generation mode (std: Standard, pro: Professional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )

            ParameterString(
                name="aspect_ratio",
                default_value="16:9",
                tooltip="Aspect ratio of the generated video frame (width:height)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16", "1:1"])},
            )

            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video Length, unit: s (seconds)",
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

        if model_id == "kling-v2-5-turbo":
            self.hide_parameter_by_name(["mode", "aspect_ratio"])
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
            current_aspect = self.get_parameter_value("aspect_ratio")
            if current_aspect != "16:9":
                self.set_parameter_value("aspect_ratio", "16:9")
            current_duration = self.get_parameter_value("duration")
            if current_duration not in [5, 10]:
                self.set_parameter_value("duration", 5)
            self.hide_parameter_by_name("sound")
        elif model_id == "kling-v2-6":
            self.hide_parameter_by_name("mode")
            self.show_parameter_by_name(["aspect_ratio", "duration", "sound"])
            current_mode = self.get_parameter_value("mode")
            if current_mode != "pro":
                self.set_parameter_value("mode", "pro")
            current_duration = self.get_parameter_value("duration")
            if current_duration not in [5, 10]:
                self.set_parameter_value("duration", 5)
        else:
            self.show_parameter_by_name(["mode", "aspect_ratio", "duration"])
            self.hide_parameter_by_name("sound")

        if model_id == V3_MODEL_ID:
            self.show_parameter_by_name("multi_shot")
        else:
            self.hide_parameter_by_name("multi_shot")
            self.hide_parameter_by_name("shot_type")
            self.hide_parameter_by_name("shot_count")
            self.hide_parameter_by_name("shots")
            for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            self.show_parameter_by_name("prompt")

    def _update_multi_shot_parameter_visibility(self) -> None:
        """Toggle prompt and shot inputs for v3 multi-shot configurations."""
        model_name = self.get_parameter_value("model_name") or "Kling v3.0"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        if model_id != V3_MODEL_ID:
            return

        is_multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"

        if not is_multi_shot:
            self.hide_parameter_by_name("shot_type")
            self.hide_parameter_by_name("shot_count")
            self.hide_parameter_by_name("shots")
            self.show_parameter_by_name("duration")
            self.show_parameter_by_name("prompt")
            for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            return

        self.show_parameter_by_name("shot_type")
        if shot_type == "intelligence":
            self.show_parameter_by_name("prompt")
            self.hide_parameter_by_name("shot_count")
            self.hide_parameter_by_name("shots")
            self.show_parameter_by_name("duration")
            for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
                self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])
            return

        # customize
        self.hide_parameter_by_name("prompt")
        self.hide_parameter_by_name("shot_count")
        self.show_parameter_by_name("shots")
        self.hide_parameter_by_name("duration")
        for shot_index in range(1, MAX_MULTI_PROMPT_COUNT + 1):
            self.hide_parameter_by_name([f"shot_{shot_index}_prompt", f"shot_{shot_index}_duration"])

    def _get_multi_shot_items_from_widget(self) -> list[dict[str, Any]]:
        """Extract and normalize multi-shot items from the widget-backed shots parameter."""
        raw_shots = self.get_parameter_value("shots")
        if not isinstance(raw_shots, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, raw_shot in enumerate(raw_shots, start=1):
            if not isinstance(raw_shot, dict):
                continue

            prompt_value = raw_shot.get("description", raw_shot.get("prompt", ""))
            prompt = str(prompt_value or "").strip()
            duration = str(raw_shot.get("duration", "") or "").strip()

            normalized.append({"index": index, "prompt": prompt, "duration": duration})

        return normalized

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Appends :text2video modality to the model name.
        """
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{model_id}:text2video"

    def _build_customize_multi_prompt_payload(self, shot_count: int) -> list[dict[str, Any]]:
        """Build multi_prompt payload from shot input parameters."""
        widget_items = self._get_multi_shot_items_from_widget()
        if widget_items:
            return widget_items

        return [
            {
                "index": shot_index,
                "prompt": (self.get_parameter_value(f"shot_{shot_index}_prompt") or "").strip(),
                "duration": str(self.get_parameter_value(f"shot_{shot_index}_duration") or "").strip(),
            }
            for shot_index in range(1, shot_count + 1)
        ]

    @staticmethod
    def _sum_multi_prompt_duration_seconds(multi_prompt: list[dict[str, Any]]) -> int | None:
        """Sum duration fields from multi_prompt items as integer seconds."""
        total_duration = Decimal(0)
        for shot in multi_prompt:
            try:
                shot_duration = Decimal(str(shot.get("duration", "") or ""))
            except InvalidOperation:
                return None

            if shot_duration < 1:
                return None
            total_duration += shot_duration

        if total_duration != total_duration.to_integral_value():
            return None

        return int(total_duration)

    def _validate_customize_multi_shot(  # noqa: C901, PLR0912, PLR0915
        self, exceptions: list[Exception], shot_count: Any, duration: Any
    ) -> None:
        """Validate customize multi-shot inputs."""
        widget_items = self._get_multi_shot_items_from_widget()
        if widget_items:
            if not (1 <= len(widget_items) <= MAX_MULTI_PROMPT_COUNT):
                exceptions.append(
                    ValueError(
                        f"{self.name} shots must contain between 1 and {MAX_MULTI_PROMPT_COUNT} items "
                        f"(got {len(widget_items)})."
                    )
                )

            total_duration = Decimal(0)
            for item in widget_items[:MAX_MULTI_PROMPT_COUNT]:
                shot_index = item["index"]
                component_prompt = item["prompt"]
                component_duration = item["duration"]

                if not component_prompt:
                    exceptions.append(ValueError(f"{self.name} shot {shot_index} prompt must be a non-empty string."))
                elif len(component_prompt) > MAX_PROMPT_LENGTH:
                    exceptions.append(
                        ValueError(
                            f"{self.name} shot {shot_index} prompt exceeds {MAX_PROMPT_LENGTH} characters "
                            f"(got: {len(component_prompt)} characters)."
                        )
                    )

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
                        ValueError(
                            f"{self.name} shot {shot_index} duration must be at least 1 (got {component_duration})."
                        )
                    )
                if component_duration_decimal != component_duration_decimal.to_integral_value():
                    exceptions.append(
                        ValueError(
                            f"{self.name} shot {shot_index} duration must be an integer number of seconds "
                            f"(got {component_duration})."
                        )
                    )
                total_duration += component_duration_decimal

            if total_duration <= 0:
                exceptions.append(
                    ValueError(
                        f"{self.name} multi-shot durations must sum to a value greater than 0 (got {total_duration})."
                    )
                )
            return

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

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Kling API.

        Returns:
            dict: The request payload (model field excluded, handled by base class)
        """
        prompt = self.get_parameter_value("prompt") or ""
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        cfg_scale = self.get_parameter_value("cfg_scale")
        mode = self.get_parameter_value("mode") or "std"
        aspect_ratio = self.get_parameter_value("aspect_ratio") or "16:9"
        duration = self.get_parameter_value("duration") or 5
        sound = self.get_parameter_value("sound") or "off"
        multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"
        shot_count = self.get_parameter_value("shot_count") or 1

        payload: dict[str, Any] = {
            "model_name": model_id,
            "duration": int(duration),
            "cfg_scale": float(cfg_scale),
            "mode": mode,
            "aspect_ratio": aspect_ratio,
        }
        if model_id == V3_MODEL_ID:
            payload["multi_shot"] = multi_shot
            if multi_shot:
                payload["shot_type"] = shot_type
                if shot_type == "customize":
                    payload["prompt"] = ""
                    try:
                        shot_count = int(shot_count)
                    except (TypeError, ValueError):
                        shot_count = 1
                    shot_count = max(1, min(MAX_MULTI_PROMPT_COUNT, shot_count))
                    payload["multi_prompt"] = self._build_customize_multi_prompt_payload(shot_count)
                    summed_duration = self._sum_multi_prompt_duration_seconds(payload["multi_prompt"])
                    if summed_duration is not None:
                        payload["duration"] = summed_duration
                else:
                    payload["prompt"] = prompt.strip()
            else:
                payload["prompt"] = prompt.strip()
        else:
            payload["prompt"] = prompt.strip()

        # Add negative_prompt if provided
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt.strip()

        # Add sound parameter for v2.6
        if model_id == "kling-v2-6" and sound:
            payload["sound"] = sound

        return payload

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
                filename = f"kling_text_to_video_{generation_id}.mp4"
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

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        # Validate prompt is provided
        prompt = self.get_parameter_value("prompt") or ""
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        multi_shot = bool(self.get_parameter_value("multi_shot"))
        shot_type = self.get_parameter_value("shot_type") or "customize"
        shot_count = self.get_parameter_value("shot_count") or 1

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
                duration = self.get_parameter_value("duration") or 5
                self._validate_customize_multi_shot(exceptions, shot_count, duration)

        # Validate negative prompt length
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        if negative_prompt and len(negative_prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} negative_prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(negative_prompt)} characters)."
                )
            )

        # Validate model-specific constraints
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        mode = self.get_parameter_value("mode") or "std"
        aspect_ratio = self.get_parameter_value("aspect_ratio") or "16:9"

        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})

        if mode not in capabilities.get("modes", ["std", "pro"]):
            valid_modes = capabilities.get("modes", [])
            exceptions.append(
                ValueError(
                    f"{self.name}: Model {model_name} does not support mode '{mode}'. "
                    f"Valid modes: {', '.join(valid_modes)}"
                )
            )

        if aspect_ratio not in capabilities.get("aspect_ratios", ["16:9", "9:16", "1:1"]):
            valid_ratios = capabilities.get("aspect_ratios", [])
            exceptions.append(
                ValueError(
                    f"{self.name}: Model {model_name} does not support aspect ratio '{aspect_ratio}'. "
                    f"Valid aspect ratios: {', '.join(valid_ratios)}"
                )
            )

        return exceptions if exceptions else None
