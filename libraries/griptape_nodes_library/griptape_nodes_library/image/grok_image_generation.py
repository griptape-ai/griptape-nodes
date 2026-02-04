from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any, ClassVar

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.static_file_events import (
    DownloadAndSaveRequest,
    DownloadAndSaveResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["GrokImageGeneration"]


class GrokImageGeneration(GriptapeProxyNode):
    """Generate images using Grok image models via Griptape model proxy.

    Inputs:
        - model (str): Grok image model to use
        - prompt (str): Prompt for image generation
        - aspect_ratio (str): Aspect ratio for generated image
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
        "Grok 2 Image": "grok-2-image-1212",
    }

    MIN_IMAGES: ClassVar[int] = 1
    MAX_IMAGES: ClassVar[int] = 10
    ASPECT_RATIO_OPTIONS: ClassVar[list[str]] = [
        "1:1",
        "3:4",
        "4:3",
        "9:16",
        "16:9",
        "2:3",
        "3:2",
        "9:19.5",
        "19.5:9",
        "9:20",
        "20:9",
        "1:2",
        "2:1",
        "auto",
    ]

    QUALITY_OPTIONS: ClassVar[list[str]] = ["low", "medium", "high"]

    RESOLUTION_OPTIONS: ClassVar[list[str]] = ["1k", "2k"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Grok image models via Griptape model proxy"

        self.add_parameter(
            ParameterString(
                name="model",
                default_value="Grok Imagine Image",
                tooltip="Select the Grok image model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["Grok Imagine Image", "Grok 2 Image"])},
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Prompt for image generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the image you want to generate...",
                allow_output=False,
            )
        )

        self.add_parameter(
            ParameterString(
                name="aspect_ratio",
                default_value="1:1",
                tooltip="Aspect ratio of the generated image",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.ASPECT_RATIO_OPTIONS)},
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
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
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
        return f"{base_model_id}:generate"

    def _get_payload_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "Grok Imagine Image"
        return self.MODEL_NAME_MAP.get(model_name, model_name)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        prompt = (self.get_parameter_value("prompt") or "").strip()
        if not prompt:
            exceptions.append(ValueError(f"{self.name}: Prompt is required for image generation."))

        n_value = self.get_parameter_value("n")
        if n_value is None or not self.MIN_IMAGES <= int(n_value) <= self.MAX_IMAGES:
            exceptions.append(ValueError(f"{self.name}: n must be between {self.MIN_IMAGES} and {self.MAX_IMAGES}."))

        return exceptions if exceptions else None

    async def _build_payload(self) -> dict[str, Any]:
        prompt = (self.get_parameter_value("prompt") or "").strip()
        aspect_ratio = self.get_parameter_value("aspect_ratio") or "1:1"
        n_value = int(self.get_parameter_value("n") or 1)
        resolution = self.get_parameter_value("resolution") or "1k"
        api_model_id = self._get_payload_model_id()

        payload: dict[str, Any] = {
            "model": api_model_id,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n_value,
            "resolution": resolution,
            "response_format": "url",
        }
        if self._supports_quality(self.get_parameter_value("model") or "Grok Imagine Image"):
            payload["quality"] = self.get_parameter_value("quality") or "medium"

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
            details = f"Image generated successfully and saved as {filenames[0]}."
        else:
            details = f"Generated {len(image_artifacts)} images successfully: {', '.join(filenames)}."

        self._set_status_results(was_successful=True, result_details=details)

    def _set_safe_defaults(self) -> None:
        for i in range(1, 11):
            param_name = "image_url" if i == 1 else f"image_url_{i}"
            self.parameter_output_values[param_name] = None

    async def _save_single_image_from_url(
        self, image_url: str, generation_id: str | None = None, index: int = 0
    ) -> ImageUrlArtifact:
        filename = (
            f"grok_image_{generation_id}_{index}.jpg" if generation_id else f"grok_image_{int(time.time())}_{index}.jpg"
        )

        result = await GriptapeNodes.ahandle_request(
            DownloadAndSaveRequest(
                url=image_url,
                filename=filename,
                artifact_type=ImageUrlArtifact,
            )
        )

        if isinstance(result, DownloadAndSaveResultSuccess):
            return result.artifact
        with suppress(Exception):
            logger.warning("%s failed to save image %s: %s", self.name, index, result.result_details)
        return ImageUrlArtifact(value=image_url)
