from __future__ import annotations

import logging
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.static_file_events import (
    DownloadAndSaveRequest,
    DownloadAndSaveResultSuccess,
    LoadAsBase64DataUriRequest,
    LoadAsBase64DataUriResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import (
    convert_image_value_to_base64_data_uri,
    resolve_localhost_url_to_path,
)

logger = logging.getLogger("griptape_nodes")

__all__ = ["GrokImageEdit"]


class GrokImageEdit(GriptapeProxyNode):
    """Edit images using Grok image models via Griptape model proxy.

    Inputs:
        - model (str): Grok image model to use
        - image (ImageUrlArtifact): Input image to edit (required)
        - prompt (str): Editing prompt
        - n (int): Number of images to generate (1-10)
        - quality (str): Output quality (low, medium, high)
        - resolution (str): Output resolution (1k, 2k)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim response from the model proxy
        - image_url (ImageUrlArtifact): First generated image
        - image_url_2 ... image_url_10 (ImageUrlArtifact): Additional images
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Grok Imagine Image": "grok-imagine-image",
    }

    MIN_IMAGES: ClassVar[int] = 1
    MAX_IMAGES: ClassVar[int] = 10
    QUALITY_OPTIONS: ClassVar[list[str]] = ["low", "medium", "high"]

    RESOLUTION_OPTIONS: ClassVar[list[str]] = ["1k", "2k"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Edit images using Grok image models via Griptape model proxy"

        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Grok Imagine Image",
                tooltip="Select the Grok image model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["Grok Imagine Image"])},
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Prompt for image editing",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the edits you want to make...",
                allow_output=False,
            )
        )

        self.add_parameter(
            ParameterImage(
                name="image",
                default_value="",
                tooltip="Input image to edit",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image"},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="n",
                default_value=1,
                tooltip="Number of images to generate (1-10)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                min_val=1,
                max_val=10,
                slider=True,
            )
        )

        self.add_parameter(
            ParameterString(
                name="quality",
                default_value="medium",
                tooltip="Quality of the output image (currently a no-op)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.QUALITY_OPTIONS)},
            )
        )

        self.add_parameter(
            ParameterString(
                name="resolution",
                default_value="1k",
                tooltip="Resolution of the generated image (only 1k currently supported)",
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

        for i in range(1, 11):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            self.add_parameter(
                ParameterImage(
                    name=param_name,
                    tooltip=f"Generated image {i}",
                    allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                    settable=False,
                    ui_options={"pulse_on_run": True, "hide": i > 1},
                )
            )

        self._create_status_parameters(
            result_details_tooltip="Details about the image editing result or any errors",
            result_details_placeholder="Editing status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )
        self._initialize_parameter_visibility()

    def _initialize_parameter_visibility(self) -> None:
        model_name = self.get_parameter_value("model") or "Grok Imagine Image"
        if self._supports_quality(model_name):
            self.show_parameter_by_name("quality")
        else:
            self.hide_parameter_by_name("quality")

    @staticmethod
    def _supports_quality(model_name: str) -> bool:
        return model_name != "Grok 2 Image"

    def after_value_set(self, parameter: Any, value: Any) -> None:
        if parameter.name == "model":
            if self._supports_quality(value):
                self.show_parameter_by_name("quality")
            else:
                self.hide_parameter_by_name("quality")
        return super().after_value_set(parameter, value)

    @staticmethod
    def _has_media_value(value: Any) -> bool:
        if value is None:
            return False
        if hasattr(value, "value"):
            return bool(value.value)
        return bool(value)

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
        except Exception:
            return None

        return None

    def _guess_image_mime_type(self, image_url: str) -> str:
        ext = Path(urlparse(image_url).path).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
        }
        return mime_map.get(ext, "image/png")

    async def _prepare_image_data_uri(self, image_input: Any) -> str | None:
        if not image_input:
            return None

        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        if image_value.startswith("data:image/"):
            return image_value

        if image_value.startswith(("http://", "https://")):
            request = LoadAsBase64DataUriRequest(
                artifact_or_url=image_value,
                context_name=f"{self.name}.input_image",
            )
            result = await GriptapeNodes.ahandle_request(request)
            if not isinstance(result, LoadAsBase64DataUriResultSuccess):
                return None
            return result.data_uri

        return convert_image_value_to_base64_data_uri(image_value, self.name)

    def _show_image_output_parameters(self, count: int) -> None:
        for i in range(1, 11):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            if i <= count:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

    def _get_api_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Image"
        base_model_id = self.MODEL_NAME_MAP.get(model_name, model_name)
        return f"{base_model_id}:edit"

    def _get_payload_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Image"
        return self.MODEL_NAME_MAP.get(model_name, model_name)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        prompt = (self.get_parameter_value("prompt") or "").strip()
        if not prompt:
            exceptions.append(ValueError(f"{self.name}: Prompt is required for image editing."))

        image_value = self.get_parameter_value("image")
        if not self._has_media_value(image_value):
            exceptions.append(ValueError(f"{self.name}: Image is required for editing."))

        n_value = self.get_parameter_value("n")
        if n_value is None or not self.MIN_IMAGES <= int(n_value) <= self.MAX_IMAGES:
            exceptions.append(ValueError(f"{self.name}: n must be between {self.MIN_IMAGES} and {self.MAX_IMAGES}."))

        return exceptions if exceptions else None

    async def _build_payload(self) -> dict[str, Any]:
        prompt = (self.get_parameter_value("prompt") or "").strip()
        n_value = int(self.get_parameter_value("n") or 1)
        resolution = self.get_parameter_value("resolution") or "1k"
        api_model_id = self._get_payload_model_id()
        image_data_uri = await self._prepare_image_data_uri(self.get_parameter_value("image"))

        payload: dict[str, Any] = {
            "model": api_model_id,
            "prompt": prompt,
            "n": n_value,
            "resolution": resolution,
            "response_format": "url",
        }
        if self._supports_quality(self.get_parameter_value("model") or "Grok Imagine Image"):
            payload["quality"] = self.get_parameter_value("quality") or "medium"

        if image_data_uri:
            payload["image"] = {"url": image_data_uri}

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        data = result_json.get("data", [])
        if not data:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no image data was found in the response.",
            )
            return

        image_artifacts: list[ImageUrlArtifact] = []
        for idx, image_data in enumerate(data):
            image_url = image_data.get("url")
            if not image_url:
                continue

            artifact = await self._save_single_image_from_url(image_url, generation_id, idx)
            if artifact:
                image_artifacts.append(artifact)

        if not image_artifacts:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no image URLs were found in the response.",
            )
            return

        self._show_image_output_parameters(len(image_artifacts))

        for idx, artifact in enumerate(image_artifacts, start=1):
            param_name = "image_url" if idx == 1 else f"image_url_{idx}"
            self.parameter_output_values[param_name] = artifact

        filenames = [artifact.name for artifact in image_artifacts]
        if len(image_artifacts) == 1:
            details = f"Image edited successfully and saved as {filenames[0]}."
        else:
            details = f"Edited {len(image_artifacts)} images successfully: {', '.join(filenames)}."

        self._set_status_results(was_successful=True, result_details=details)

    def _set_safe_defaults(self) -> None:
        for i in range(1, 11):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            self.parameter_output_values[param_name] = None

    async def _save_single_image_from_url(
        self, image_url: str, generation_id: str | None = None, index: int = 0
    ) -> ImageUrlArtifact:
        filename = (
            f"grok_image_edit_{generation_id}_{index}.jpg"
            if generation_id
            else f"grok_image_edit_{int(time.time())}_{index}.jpg"
        )

        request = DownloadAndSaveRequest(
            url=image_url,
            filename=filename,
            artifact_type=ImageUrlArtifact,
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, DownloadAndSaveResultSuccess):
            return result.artifact
        with suppress(Exception):
            logger.warning("%s failed to save image %s: %s", self.name, index, result.result_details)
        return ImageUrlArtifact(value=image_url)
