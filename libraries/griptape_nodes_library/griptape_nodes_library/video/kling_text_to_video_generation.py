from __future__ import annotations

import logging
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import FileWriteError
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingTextToVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500


class KlingTextToVideoGeneration(GriptapeProxyNode):
    """Generate a video from text using Kling AI models via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for video generation (max 2500 chars)
        - model_name (str): Model to use (default: Kling v2.6)
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
        "Kling v2.6": "kling-v2-6",
        "Kling v2.5 Turbo": "kling-v2-5-turbo",
        "Kling v2.1 Master": "kling-v2-1-master",
        "Kling v2 Master": "kling-v2-master",
        "Kling v1.6": "kling-v1-6",
    }

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
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
                default_value="Kling v2.6",
                tooltip="Model Name",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
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
        self._output_file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="kling_t2v.mp4",
        )
        self._output_file_param.add_parameter()

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

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Appends :text2video modality to the model name.
        """
        model_name = self.get_parameter_value("model_name") or "Kling v2.6"
        model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{model_id}:text2video"

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

        payload: dict[str, Any] = {
            "prompt": prompt.strip(),
            "model_name": model_id,
            "duration": int(duration),
            "cfg_scale": float(cfg_scale),
            "mode": mode,
            "aspect_ratio": aspect_ratio,
        }

        # Add negative_prompt if provided
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt.strip()

        # Add sound parameter for v2.6
        if model_id == "kling-v2-6" and sound:
            payload["sound"] = sound

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:  # noqa: ARG002
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
            output_file = self._output_file_param.build_file()
            try:
                actual_path = await output_file.awrite_bytes(video_bytes)
            except FileWriteError as e:
                self._log(f"Failed to write video: {e}")
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save video: {e}).",
                )
                return
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=actual_path, name=actual_path.name)
            logger.info("%s saved video as %s", self.name, actual_path)
            self._set_status_results(
                was_successful=True,
                result_details=f"Video generated successfully and saved as {actual_path.name}.",
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
        if not prompt.strip():
            exceptions.append(ValueError(f"{self.name} requires a prompt to generate video."))

        # Validate prompt length
        if len(prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(prompt)} characters)."
                )
            )

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
