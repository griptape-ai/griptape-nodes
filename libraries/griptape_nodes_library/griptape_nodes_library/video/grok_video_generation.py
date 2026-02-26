from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["GrokVideoGeneration"]


class GrokVideoGeneration(GriptapeProxyNode):
    """Generate videos using Grok video models via Griptape model proxy.

    Inputs:
        - model (str): Grok video model to use
        - prompt (str): Prompt for video generation
        - aspect_ratio (str): Aspect ratio for generated video
        - duration (int): Video duration in seconds (1-15)
        - image (ImageUrlArtifact): Optional first frame image for image-to-video
        - resolution (str): Output resolution (480p, 720p)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim response from the model proxy
        - video_url (VideoUrlArtifact): Generated video
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Grok Imagine Video": "grok-imagine-video",
    }

    MIN_DURATION: ClassVar[int] = 1
    MAX_DURATION: ClassVar[int] = 15
    ASPECT_RATIO_OPTIONS: ClassVar[list[str]] = [
        "1:1",
        "16:9",
        "9:16",
        "4:3",
        "3:4",
        "3:2",
        "2:3",
    ]

    RESOLUTION_OPTIONS: ClassVar[list[str]] = ["480p", "720p"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate videos using Grok video models via Griptape model proxy"

        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Grok Imagine Video",
                tooltip="Select the Grok video model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["Grok Imagine Video"])},
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Prompt for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the video you want to generate...",
                allow_output=False,
            )
        )

        self.add_parameter(
            ParameterImage(
                name="image",
                default_value="",
                tooltip="Optional first frame image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        self.add_parameter(
            ParameterString(
                name="aspect_ratio",
                default_value="16:9",
                tooltip="Aspect ratio of the generated video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.ASPECT_RATIO_OPTIONS)},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="duration",
                default_value=6,
                tooltip="Video duration in seconds (1-15)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                min_val=1,
                max_val=15,
                slider=True,
            )
        )

        self.add_parameter(
            ParameterString(
                name="resolution",
                default_value="720p",
                tooltip="Resolution of the generated video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.RESOLUTION_OPTIONS)},
            )
        )

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
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
            ParameterVideo(
                name="video_url",
                tooltip="Generated video",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    @staticmethod
    def _has_media_value(value: Any) -> bool:
        if value is None:
            return False
        if hasattr(value, "value"):
            return bool(value.value)
        return bool(value)

    def _extract_image_value(self, image_input: Any) -> str | None:
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
        except Exception:
            return None

        return None

    async def _prepare_image_data_uri(self, image_input: Any) -> str | None:
        if not image_input:
            return None

        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        try:
            return await File(image_value).aread_data_uri(fallback_mime="image/png")
        except FileLoadError:
            logger.debug("%s failed to load image value: %s", self.name, image_value)
            return None

    def _get_api_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Video"
        base_model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{base_model_id}:generate"

    def _get_payload_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Video"
        return self.MODEL_NAME_MAP.get(model_name, model_name)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        prompt = (self.get_parameter_value("prompt") or "").strip()
        if not prompt:
            exceptions.append(ValueError(f"{self.name}: Prompt is required for video generation."))

        duration = self.get_parameter_value("duration")
        if duration is None or not self.MIN_DURATION <= int(duration) <= self.MAX_DURATION:
            exceptions.append(
                ValueError(
                    f"{self.name}: duration must be between {self.MIN_DURATION} and {self.MAX_DURATION} seconds."
                )
            )

        return exceptions if exceptions else None

    async def _build_payload(self) -> dict[str, Any]:
        prompt = (self.get_parameter_value("prompt") or "").strip()
        aspect_ratio = self.get_parameter_value("aspect_ratio") or "16:9"
        duration = int(self.get_parameter_value("duration") or 6)
        resolution = self.get_parameter_value("resolution") or "720p"
        api_model_id = self._get_payload_model_id()
        image_data_uri = await self._prepare_image_data_uri(self.get_parameter_value("image"))

        payload: dict[str, Any] = {
            "model": api_model_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
        }

        if image_data_uri:
            payload["image"] = {"url": image_data_uri}

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        video_info = result_json.get("video") or {}
        video_url = video_info.get("url")

        if not video_url:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no video URL was found in the response.",
            )
            return

        try:
            video_bytes = await self._download_bytes_from_url(video_url)
        except Exception as e:
            with suppress(Exception):
                logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"grok_video_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
            except (OSError, PermissionError) as e:
                with suppress(Exception):
                    logger.warning("%s failed to save video: %s", self.name, e)
            else:
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully and saved as {filename}.",
                )
                return

        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)
        self._set_status_results(
            was_successful=True,
            result_details="Video generated successfully. Using provider URL (could not save to static storage).",
        )

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["video_url"] = None
