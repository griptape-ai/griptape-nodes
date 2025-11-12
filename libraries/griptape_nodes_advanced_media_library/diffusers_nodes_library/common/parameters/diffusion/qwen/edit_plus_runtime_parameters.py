import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from griptape.artifacts import ImageUrlArtifact
from PIL.Image import Image
from pillow_nodes_library.utils import (  # type: ignore[reportMissingImports]
    image_artifact_to_pil,
)
from utils.image_utils import load_image_from_url_artifact

from diffusers_nodes_library.common.parameters.diffusion.qwen.common import qwen_latents_to_image_pil
from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")

MAX_IMAGES = 3


class QwenImageEditPlusPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["list"],
                type="list[ImageArtifact]",
                tooltip="List of 1-3 images to be edited.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image editing.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts not to guide the image editing.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=4.0,
                type="float",
                tooltip="Higher guidance_scale encourages a model to generate images more aligned with prompt at the expense of lower image quality.",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("guidance_scale")
        self._node.remove_parameter_element_by_name("image")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

        # Validate image count (1-3 images required)
        if parameter.name == "image" and value is not None:
            if not isinstance(value, list):
                msg = f"QwenImageEditPlusPipeline requires a list of images, got {type(value).__name__}"
                raise ValueError(msg)
            if len(value) < 1 or len(value) > MAX_IMAGES:
                msg = f"QwenImageEditPlusPipeline requires 1-{MAX_IMAGES} images, got {len(value)}"
                raise ValueError(msg)

    def get_image_pil(self) -> list[Image]:
        input_image_artifact = self._node.get_parameter_value("image")

        # Handle list of images (only supported mode)
        if not isinstance(input_image_artifact, list):
            msg = f"QwenImageEditPlusPipeline requires a list of images, got {type(input_image_artifact).__name__}"
            raise TypeError(msg)

        images = []
        for artifact in input_image_artifact:
            image_artifact = artifact
            if isinstance(image_artifact, ImageUrlArtifact):
                image_artifact = load_image_from_url_artifact(image_artifact)
            pil_image = image_artifact_to_pil(image_artifact)
            images.append(pil_image.convert("RGB"))
        return images

    def _get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_image_pil(),
        }

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        return qwen_latents_to_image_pil(pipe, latents, self.get_height(), self.get_width())
