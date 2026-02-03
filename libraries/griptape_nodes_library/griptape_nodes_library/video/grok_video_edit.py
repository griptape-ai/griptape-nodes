from __future__ import annotations

import base64
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.utils.url_utils import is_url_or_path
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import resolve_localhost_url_to_path

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
            return resolve_localhost_url_to_path(video_input)

        try:
            if hasattr(video_input, "value"):
                value = getattr(video_input, "value", None)
                if isinstance(value, str):
                    return resolve_localhost_url_to_path(value)
            if hasattr(video_input, "base64"):
                b64 = getattr(video_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception:
            return None

        return None

    def _guess_video_mime_type(self, video_url: str) -> str:
        ext = Path(urlparse(video_url).path).suffix.lower()
        content_type_map = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".m4v": "video/mp4",
        }
        return content_type_map.get(ext, "video/mp4")

    async def _download_and_encode_video(self, url: str) -> str | None:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException):
                return None
            else:
                content_type = (resp.headers.get("content-type") or "video/mp4").split(";")[0]
                if not content_type.startswith("video/"):
                    content_type = self._guess_video_mime_type(url)
                b64 = base64.b64encode(resp.content).decode("utf-8")
                return f"data:{content_type};base64,{b64}"

    async def _read_local_video_and_encode(self, video_value: str) -> str | None:
        try:
            workspace_path = GriptapeNodes.ConfigManager().workspace_path
            file_path = workspace_path / video_value
            if not file_path.exists() or not file_path.is_file():
                file_path = Path(video_value)
                if not file_path.exists() or not file_path.is_file():
                    return None

            video_bytes = file_path.read_bytes()
            if not video_bytes:
                return None
        except (OSError, PermissionError):
            return None
        else:
            content_type = self._guess_video_mime_type(str(file_path))
            b64 = base64.b64encode(video_bytes).decode("utf-8")
            return f"data:{content_type};base64,{b64}"

    async def _prepare_video_data_uri(self, video_input: Any) -> str | None:
        if not video_input:
            return None

        video_value = self._extract_video_value(video_input)
        if not video_value:
            return None

        # If it's not a URL or path, assume it's inline data (data URI)
        if not is_url_or_path(video_value):
            return video_value

        # Handle HTTP/HTTPS URLs - download and convert
        if video_value.startswith(("http://", "https://")):
            return await self._download_and_encode_video(video_value)

        # Handle local file paths
        data_uri = await self._read_local_video_and_encode(video_value)
        if data_uri:
            return data_uri
        return f"data:video/mp4;base64,{video_value}"

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
                saved_url = static_files_manager.save_static_file(video_bytes, filename, use_direct_save=True)
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
