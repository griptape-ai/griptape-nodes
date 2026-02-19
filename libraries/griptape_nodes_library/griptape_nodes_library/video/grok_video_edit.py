from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["GrokVideoEdit"]


class GrokVideoEdit(GriptapeProxyNode):
    """Edit videos using Grok video models via Griptape model proxy.

    Inputs:
        - model (str): Grok video model to use
        - prompt (str): Prompt for video editing
        - video (VideoUrlArtifact): Input video to edit (required)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim response from the model proxy
        - video_url (VideoUrlArtifact): Edited video
        - was_successful (bool): Whether the edit succeeded
        - result_details (str): Details about the edit result or error
    """

    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Grok Imagine Video": "grok-imagine-video",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Edit videos using Grok video models via Griptape model proxy"

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
                tooltip="Prompt for video editing",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the edits you want to make...",
                allow_output=False,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video",
                default_value="",
                tooltip="Input video to edit",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Video"},
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
                tooltip="Edited video",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        self._create_status_parameters(
            result_details_tooltip="Details about the video editing result or any errors",
            result_details_placeholder="Editing status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    @staticmethod
    def _has_media_value(value: Any) -> bool:
        if value is None:
            return False
        if hasattr(value, "value"):
            return bool(value.value)
        return bool(value)

    def _extract_video_value(self, video_input: Any) -> str | None:
        if isinstance(video_input, str):
            return video_input

        try:
            if hasattr(video_input, "value"):
                value = getattr(video_input, "value", None)
                if isinstance(value, str):
                    return value
            if hasattr(video_input, "base64"):
                b64 = getattr(video_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception:
            return None

        return None

    async def _prepare_video_data_uri(self, video_input: Any) -> str | None:
        if not video_input:
            return None

        video_value = self._extract_video_value(video_input)
        if not video_value:
            return None

        if video_value.startswith("data:"):
            return video_value

        try:
            return await File(video_value).aread_data_uri(fallback_mime="video/mp4")
        except FileLoadError:
            return None

    def _get_api_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Video"
        base_model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{base_model_id}:edit"

    def _get_payload_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Video"
        return self.MODEL_NAME_MAP.get(model_name, model_name)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        prompt = (self.get_parameter_value("prompt") or "").strip()
        if not prompt:
            exceptions.append(ValueError(f"{self.name}: Prompt is required for video editing."))

        video_value = self.get_parameter_value("video")
        if not self._has_media_value(video_value):
            exceptions.append(ValueError(f"{self.name}: Video is required for editing."))

        return exceptions if exceptions else None

    async def _build_payload(self) -> dict[str, Any]:
        prompt = (self.get_parameter_value("prompt") or "").strip()
        api_model_id = self._get_payload_model_id()
        video_data_uri = await self._prepare_video_data_uri(self.get_parameter_value("video"))

        payload: dict[str, Any] = {
            "model": api_model_id,
            "prompt": prompt,
        }

        if video_data_uri:
            payload["video"] = {"url": video_data_uri}

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        video_info = result_json.get("video") or {}
        video_url = video_info.get("url")
        video_info.get("duration")

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
                filename = f"grok_video_edit_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
            except (OSError, PermissionError) as e:
                with suppress(Exception):
                    logger.warning("%s failed to save video: %s", self.name, e)
            else:
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video edited successfully and saved as {filename}.",
                )
                return

        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)
        self._set_status_results(
            was_successful=True,
            result_details="Video edited successfully. Using provider URL (could not save to static storage).",
        )

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["video_url"] = None
