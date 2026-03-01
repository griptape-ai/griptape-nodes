from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from griptape.artifacts import ImageArtifact, ImageUrlArtifact, VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.splat.splat_artifact import SplatUrlArtifact
from griptape_nodes_library.utils.image_utils import (
    load_image_from_url_artifact,
    resolve_localhost_url_to_path,
)

logger = logging.getLogger("griptape_nodes")

__all__ = ["WorldLabsSplatGeneration"]

MODEL_NAME_MAP = {
    "Marble 0.1-mini": "marble-0.1-mini",
    "Marble 0.1-plus": "marble-0.1-plus",
}

PROMPT_TYPE_OPTIONS = ["text", "image", "multi-image", "video"]

MIME_EXTENSION_MAP = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-msvideo": "avi",
}


class WorldLabsSplatGeneration(GriptapeProxyNode):
    """Generate world splats with World Labs Marble models via Griptape model proxy.

    Inputs:
        - model (str): Model selection (Marble 0.1-mini, Marble 0.1-plus)
        - prompt_type (str): Prompt type (text, image, multi-image, video)
        - text_prompt (str): Text guidance (required for text, optional for others)
        - disable_recaption (bool): Disable auto-recaptioning
        - image_prompt (ImageArtifact|ImageUrlArtifact|str): Image prompt (image type only)
        - is_pano (bool): Whether the provided image is already a panorama (image type only)
        - multi_image_prompt_images (list): Images for multi-image prompt
        - multi_image_prompt_azimuths (list): Optional azimuth angles (degrees) for each multi-image input
        - reconstruct_images (bool): Enable reconstruction mode for multi-image prompt
        - video_prompt (VideoUrlArtifact|str): Video prompt (video type only)
        - seed (int): Random seed (must be > 0)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim response from the model proxy
        - thumbnail (ImageArtifact): Generated thumbnail image
        - splat_100k (SplatUrlArtifact): 100k splat asset
        - splat_500k (SplatUrlArtifact): 500k splat asset
        - splat_full_res (SplatUrlArtifact): Full resolution splat asset
        - caption (str): Generated caption text
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate World Labs splats using Marble models via Griptape model proxy"

        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Marble 0.1-mini",
                tooltip="Select the Marble model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=list(MODEL_NAME_MAP.keys()))},
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt_type",
                default_value="text",
                tooltip="Select the prompt input type",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=PROMPT_TYPE_OPTIONS)},
                ui_options={"display_name": "type"},
            )
        )

        self.add_parameter(
            ParameterBool(
                name="disable_recaption",
                default_value=False,
                tooltip="If true, use text_prompt as-is without recaptioning",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "disable_recaption"},
            )
        )

        self.add_parameter(
            ParameterString(
                name="text_prompt",
                tooltip="Text guidance (required for text prompt; optional otherwise)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the world to generate...",
                ui_options={"display_name": "text_prompt"},
            )
        )

        self.add_parameter(
            ParameterImage(
                name="image_prompt",
                tooltip="Image prompt for world generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "image_prompt"},
            )
        )

        self.add_parameter(
            ParameterBool(
                name="is_pano",
                default_value=False,
                tooltip="Whether the provided image is already a panorama",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "is_pano"},
            )
        )

        self.add_parameter(
            ParameterList(
                name="multi_image_prompt_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                ],
                default_value=[],
                tooltip="Images for the multi-image prompt",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"expander": True, "display_name": "multi_image_prompt"},
            )
        )

        self.add_parameter(
            ParameterList(
                name="multi_image_prompt_azimuths",
                input_types=["float", "int", "str", "list", "list[float]", "list[int]"],
                default_value=[],
                tooltip="Optional azimuth angles (degrees) aligned with multi-image inputs",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"expander": True, "display_name": "multi_image_prompt.azimuth"},
            )
        )

        self.add_parameter(
            ParameterBool(
                name="reconstruct_images",
                default_value=False,
                tooltip="Enable reconstruction mode for multi-image inputs",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "reconstruct_images"},
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video_prompt",
                tooltip="Video prompt for world generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "video_prompt"},
            )
        )

        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from the model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            Parameter(
                name="thumbnail",
                tooltip="Generated thumbnail image",
                type="ImageArtifact",
                output_type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display": "image", "pulse_on_run": True},
                settable=False,
            )
        )

        self.add_parameter(
            Parameter(
                name="splat_100k",
                tooltip="100k splat asset",
                type="SplatUrlArtifact",
                output_type="SplatUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "display_name": "100k",
                    "display": "splat",
                    "pulse_on_run": True,
                    "clickable_file_browser": False,
                    "expander": True,
                    "is_full_width": False,
                },
                settable=False,
            )
        )

        self.add_parameter(
            Parameter(
                name="splat_500k",
                tooltip="500k splat asset",
                type="SplatUrlArtifact",
                output_type="SplatUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "display_name": "500k",
                    "display": "splat",
                    "pulse_on_run": True,
                    "clickable_file_browser": False,
                    "expander": True,
                    "is_full_width": False,
                },
                settable=False,
            )
        )

        self.add_parameter(
            Parameter(
                name="splat_full_res",
                tooltip="Full resolution splat asset",
                type="SplatUrlArtifact",
                output_type="SplatUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "display_name": "full",
                    "display": "splat",
                    "pulse_on_run": True,
                    "clickable_file_browser": False,
                    "expander": True,
                    "is_full_width": False,
                },
                settable=False,
            )
        )

        self.add_parameter(
            ParameterString(
                name="caption",
                tooltip="Generated caption text",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Caption will appear here."},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the world generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        self._initialize_prompt_type_visibility()

    def _initialize_prompt_type_visibility(self) -> None:
        prompt_type = self.get_parameter_value("prompt_type") or "text"
        self._update_prompt_type_visibility(prompt_type)

    def _update_prompt_type_visibility(self, prompt_type: str) -> None:
        if prompt_type == "text":
            self.hide_parameter_by_name(["image_prompt", "is_pano"])
            self.hide_parameter_by_name(
                ["multi_image_prompt_images", "multi_image_prompt_azimuths", "reconstruct_images"]
            )
            self.hide_parameter_by_name("video_prompt")
        elif prompt_type == "image":
            self.show_parameter_by_name(["image_prompt", "is_pano"])
            self.hide_parameter_by_name(
                ["multi_image_prompt_images", "multi_image_prompt_azimuths", "reconstruct_images"]
            )
            self.hide_parameter_by_name("video_prompt")
        elif prompt_type == "multi-image":
            self.hide_parameter_by_name(["image_prompt", "is_pano"])
            self.show_parameter_by_name(
                ["multi_image_prompt_images", "multi_image_prompt_azimuths", "reconstruct_images"]
            )
            self.hide_parameter_by_name("video_prompt")
        elif prompt_type == "video":
            self.hide_parameter_by_name(["image_prompt", "is_pano"])
            self.hide_parameter_by_name(
                ["multi_image_prompt_images", "multi_image_prompt_azimuths", "reconstruct_images"]
            )
            self.show_parameter_by_name("video_prompt")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "prompt_type":
            self._update_prompt_type_visibility(str(value))

        self._seed_parameter.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def _get_api_model_id(self) -> str:
        model = self.get_parameter_value("model") or "Marble 0.1-mini"
        return MODEL_NAME_MAP.get(model, model)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        prompt_type = self.get_parameter_value("prompt_type") or "text"
        text_prompt = (self.get_parameter_value("text_prompt") or "").strip()

        if prompt_type not in PROMPT_TYPE_OPTIONS:
            exceptions.append(ValueError(f"{self.name}: Unsupported prompt_type '{prompt_type}'."))

        if prompt_type == "text" and not text_prompt:
            exceptions.append(ValueError(f"{self.name}: text_prompt is required for text prompt type."))

        if prompt_type == "image" and not self.get_parameter_value("image_prompt"):
            exceptions.append(ValueError(f"{self.name}: image_prompt is required for image prompt type."))

        if prompt_type == "multi-image":
            images = self.get_parameter_value("multi_image_prompt_images") or []
            if not isinstance(images, list) or len([i for i in images if i]) == 0:
                exceptions.append(ValueError(f"{self.name}: At least one multi-image prompt image is required."))

        if prompt_type == "video" and not self.get_parameter_value("video_prompt"):
            exceptions.append(ValueError(f"{self.name}: video_prompt is required for video prompt type."))

        if not self.get_parameter_value("randomize_seed"):
            seed = int(self.get_parameter_value("seed") or 0)
            if seed <= 0:
                exceptions.append(ValueError(f"{self.name}: seed must be > 0."))

        return exceptions

    async def _build_payload(self) -> dict[str, Any]:
        seed = self._normalize_seed()
        world_prompt = await self._build_world_prompt()

        payload: dict[str, Any] = {
            "model": self._get_api_model_id(),
            "seed": seed,
            "world_prompt": world_prompt,
        }

        return payload

    def _normalize_seed(self) -> int:
        self._seed_parameter.preprocess()
        seed = int(self.get_parameter_value("seed") or 0)
        if seed > 0:
            return seed
        seed = 1
        self.set_parameter_value("seed", seed)
        self.publish_update_to_parameter("seed", seed)
        return seed

    async def _build_world_prompt(self) -> dict[str, Any]:
        prompt_type = self.get_parameter_value("prompt_type") or "text"
        world_prompt: dict[str, Any] = {"type": prompt_type}

        disable_recaption = self.get_parameter_value("disable_recaption")
        if disable_recaption is not None:
            world_prompt["disable_recaption"] = bool(disable_recaption)

        text_prompt = self.get_parameter_value("text_prompt")
        if text_prompt:
            world_prompt["text_prompt"] = text_prompt

        if prompt_type == "image":
            world_prompt.update(await self._build_image_prompt())
        elif prompt_type == "multi-image":
            world_prompt.update(await self._build_multi_image_prompt())
        elif prompt_type == "video":
            world_prompt.update(await self._build_video_prompt())

        return world_prompt

    async def _build_image_prompt(self) -> dict[str, Any]:
        image_data = await self._process_input_image(self.get_parameter_value("image_prompt"))
        if not image_data:
            msg = f"{self.name}: Failed to process image_prompt."
            raise ValueError(msg)

        payload: dict[str, Any] = {"image_prompt": image_data}
        is_pano = self.get_parameter_value("is_pano")
        if is_pano is not None:
            payload["is_pano"] = bool(is_pano)
        return payload

    async def _build_multi_image_prompt(self) -> dict[str, Any]:
        multi_images = self.get_parameter_value("multi_image_prompt_images") or []
        azimuths = self._coerce_azimuth_list(self.get_parameter_value("multi_image_prompt_azimuths") or [])

        image_items: list[dict[str, Any]] = []
        for idx, image_input in enumerate(multi_images):
            if not image_input:
                continue
            image_data = await self._process_input_image(image_input)
            if not image_data:
                msg = f"{self.name}: Failed to process multi-image prompt at index {idx}."
                raise ValueError(msg)

            item: dict[str, Any] = {"content": image_data}
            if idx < len(azimuths) and azimuths[idx] is not None:
                item["azimuth"] = azimuths[idx]
            image_items.append(item)

        if not image_items:
            msg = f"{self.name}: No valid multi-image prompt inputs were provided."
            raise ValueError(msg)

        payload: dict[str, Any] = {"multi_image_prompt": image_items}
        reconstruct_images = self.get_parameter_value("reconstruct_images")
        if reconstruct_images is not None:
            payload["reconstruct_images"] = bool(reconstruct_images)
        return payload

    async def _build_video_prompt(self) -> dict[str, Any]:
        video_data = await self._process_input_video(self.get_parameter_value("video_prompt"))
        if not video_data:
            msg = f"{self.name}: Failed to process video_prompt."
            raise ValueError(msg)
        return {"video_prompt": video_data}

    async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
        response = self._extract_response_payload(result_json)
        assets = response.get("assets", {}) if isinstance(response, dict) else {}

        thumbnail_url = None
        if isinstance(assets, dict):
            thumbnail_url = assets.get("thumbnail_url")

        caption_text = assets.get("caption") if isinstance(assets, dict) else None

        splat_100k_url = None
        splat_500k_url = None
        splat_full_res_url = None
        if isinstance(assets, dict):
            splats = assets.get("splats", {})
            if isinstance(splats, dict):
                spz_urls = splats.get("spz_urls", {})
                if isinstance(spz_urls, dict):
                    splat_100k_url = spz_urls.get("100k")
                    splat_500k_url = spz_urls.get("500k")
                    splat_full_res_url = spz_urls.get("full_res")

        self.parameter_output_values["thumbnail"] = await self._build_thumbnail_artifact(thumbnail_url)
        self.parameter_output_values["splat_100k"] = (
            SplatUrlArtifact(value=splat_100k_url) if isinstance(splat_100k_url, str) and splat_100k_url else None
        )
        self.parameter_output_values["splat_500k"] = (
            SplatUrlArtifact(value=splat_500k_url) if isinstance(splat_500k_url, str) and splat_500k_url else None
        )
        self.parameter_output_values["splat_full_res"] = (
            SplatUrlArtifact(value=splat_full_res_url)
            if isinstance(splat_full_res_url, str) and splat_full_res_url
            else None
        )
        if isinstance(caption_text, str):
            self.parameter_output_values["caption"] = caption_text
        elif caption_text is None:
            self.parameter_output_values["caption"] = ""
        else:
            self.parameter_output_values["caption"] = json.dumps(caption_text, ensure_ascii=True)

        self._set_status_results(
            was_successful=True,
            result_details="World generation completed successfully.",
        )

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["thumbnail"] = None
        self.parameter_output_values["splat_100k"] = None
        self.parameter_output_values["splat_500k"] = None
        self.parameter_output_values["splat_full_res"] = None
        self.parameter_output_values["caption"] = ""

    def _extract_response_payload(self, result_json: dict[str, Any]) -> dict[str, Any]:
        response = result_json.get("response")
        if isinstance(response, dict):
            return response
        return result_json

    async def _build_thumbnail_artifact(self, thumbnail_url: str | None) -> ImageArtifact | None:
        if not thumbnail_url:
            return None

        try:
            url_artifact = ImageUrlArtifact(value=thumbnail_url)
            return load_image_from_url_artifact(url_artifact)
        except Exception as e:
            logger.debug("%s failed to load thumbnail: %s", self.name, e)
            return None

    async def _process_input_image(self, image_input: Any) -> dict[str, Any] | None:
        if not image_input:
            return None

        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        data_uri = await self._convert_to_base64_data_uri(image_value)
        if not data_uri:
            return None

        data_base64, extension = self._extract_base64_and_extension(data_uri)
        if not data_base64:
            return None

        payload: dict[str, Any] = {
            "data_base64": data_base64,
            "source": "data_base64",
        }
        if extension:
            payload["extension"] = extension

        return payload

    async def _process_input_video(self, video_input: Any) -> dict[str, Any] | None:
        if not video_input:
            return None

        data_uri = await self._convert_video_to_data_uri(video_input)
        if not data_uri:
            return None

        data_base64, extension = self._extract_base64_and_extension(data_uri)
        if not data_base64:
            return None

        payload: dict[str, Any] = {
            "data_base64": data_base64,
            "source": "data_base64",
        }
        if extension:
            payload["extension"] = extension

        return payload

    def _extract_image_value(self, image_input: Any) -> str | None:
        if isinstance(image_input, str):
            return resolve_localhost_url_to_path(image_input)

        try:
            if hasattr(image_input, "value"):
                value = getattr(image_input, "value", None)
                if isinstance(value, str):
                    return resolve_localhost_url_to_path(value)

            if hasattr(image_input, "base64"):
                b64 = getattr(image_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception as e:
            logger.error("Failed to extract image value: %s", e)

        return None

    async def _convert_to_base64_data_uri(self, image_value: str) -> str | None:
        if image_value.startswith("data:image/"):
            return image_value

        try:
            return await File(image_value).aread_data_uri(fallback_mime="image/png")
        except FileLoadError:
            logger.debug("%s failed to load image value: %s", self.name, image_value)
            return None

    async def _convert_video_to_data_uri(self, video_input: Any) -> str | None:
        video_value = self._extract_video_value(video_input)
        if not video_value:
            return None

        if video_value.startswith("data:video/"):
            return video_value

        if video_value.startswith(("http://", "https://")):
            return await self._download_and_encode_video(video_value)

        local_data = await self._read_local_video_and_encode(video_value)
        if local_data:
            return local_data

        return f"data:video/mp4;base64,{video_value}"

    @staticmethod
    def _extract_video_value(video_input: Any) -> str | None:
        if isinstance(video_input, VideoUrlArtifact):
            return video_input.value

        if isinstance(video_input, str):
            value = video_input.strip()
            return value or None

        try:
            value = getattr(video_input, "value", None)
            if isinstance(value, str) and value.strip():
                return value.strip()

            b64 = getattr(video_input, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:video/") else f"data:video/mp4;base64,{b64}"
        except Exception:
            return None

        return None

    async def _download_and_encode_video(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=60)
                resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug("%s failed to download video URL: %s", self.name, e)
            return None
        else:
            content_type = (resp.headers.get("content-type") or "video/mp4").split(";")[0]
            if not content_type.startswith("video/"):
                content_type = "video/mp4"
            b64 = base64.b64encode(resp.content).decode("utf-8")
            return f"data:{content_type};base64,{b64}"

    async def _read_local_video_and_encode(self, url_or_path: str) -> str | None:
        try:
            workspace_path = GriptapeNodes.ConfigManager().workspace_path
            parsed = urlparse(url_or_path)
            path_candidate = Path(parsed.path) if parsed.scheme else Path(url_or_path)

            # Try workspace-relative first
            file_path = workspace_path / path_candidate
            if not file_path.exists():
                file_path = path_candidate

            if not file_path.exists() or not file_path.is_file():
                return None

            video_bytes = file_path.read_bytes()
            if not video_bytes:
                return None

            ext = file_path.suffix.lower()
            content_type = {
                ".mp4": "video/mp4",
                ".mov": "video/quicktime",
                ".avi": "video/x-msvideo",
                ".webm": "video/webm",
                ".mkv": "video/x-matroska",
            }.get(ext, "video/mp4")

        except Exception as e:
            logger.debug("%s failed to read local video file: %s", self.name, e)
            return None
        else:
            b64 = base64.b64encode(video_bytes).decode("utf-8")
            return f"data:{content_type};base64,{b64}"

    @staticmethod
    def _extract_base64_and_extension(data_uri: str) -> tuple[str, str | None]:
        if not isinstance(data_uri, str):
            return "", None

        if not data_uri.startswith("data:"):
            return data_uri, None

        header, _, b64_data = data_uri.partition(",")
        if not b64_data:
            return "", None

        mime_type = None
        try:
            mime_type = header.split(":", 1)[1].split(";", 1)[0]
        except Exception:
            mime_type = None

        extension = MIME_EXTENSION_MAP.get(mime_type or "", None)
        return b64_data, extension

    @staticmethod
    def _coerce_azimuth_list(values: Any) -> list[float | None]:
        if not isinstance(values, list):
            return []

        azimuths: list[float | None] = []
        for val in values:
            if val is None:
                azimuths.append(None)
                continue
            try:
                azimuths.append(float(val))
            except (TypeError, ValueError):
                azimuths.append(None)
        return azimuths
