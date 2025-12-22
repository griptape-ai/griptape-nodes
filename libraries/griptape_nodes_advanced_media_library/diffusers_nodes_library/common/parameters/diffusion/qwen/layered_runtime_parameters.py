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
from griptape_nodes.traits.options import Options

logger = logging.getLogger("diffusers_nodes_library")

DEFAULT_RESOLUTION = 640
RESOLUTION_OPTIONS = [DEFAULT_RESOLUTION, 1024]


class QwenLayeredPipelineRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input RGBA image to decompose into layers.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                type="str",
                tooltip="The prompt or prompts to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value=" ",
                type="str",
                tooltip="The prompt or prompts not to guide the image generation.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="true_cfg_scale",
                default_value=4.0,
                type="float",
                tooltip="True classifier-free guidance scale.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="layers",
                default_value=4,
                type="int",
                tooltip="Number of image layers to generate.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="resolution",
                default_value=DEFAULT_RESOLUTION,
                type="int",
                traits={Options(choices=RESOLUTION_OPTIONS)},
                tooltip=f"Resolution bucket. {DEFAULT_RESOLUTION} is recommended for this version.",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="cfg_normalize",
                default_value=True,
                type="bool",
                tooltip="Whether to enable cfg normalization.",
                hide=True,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="use_en_prompt",
                default_value=True,
                type="bool",
                tooltip="Automatic caption language if user does not provide caption.",
                hide=True,
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("image")
        self._node.remove_parameter_element_by_name("prompt")
        self._node.remove_parameter_element_by_name("negative_prompt")
        self._node.remove_parameter_element_by_name("true_cfg_scale")
        self._node.remove_parameter_element_by_name("layers")
        self._node.remove_parameter_element_by_name("resolution")
        self._node.remove_parameter_element_by_name("cfg_normalize")
        self._node.remove_parameter_element_by_name("use_en_prompt")

    def get_image_pil(self) -> Image:
        input_image_artifact = self._node.get_parameter_value("image")
        if isinstance(input_image_artifact, ImageUrlArtifact):
            input_image_artifact = load_image_from_url_artifact(input_image_artifact)
        input_image_pil = image_artifact_to_pil(input_image_artifact)
        return input_image_pil.convert("RGBA")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "image": self.get_image_pil(),
            "prompt": self._node.get_parameter_value("prompt") or None,
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "layers": self._node.get_parameter_value("layers"),
            "resolution": self._node.get_parameter_value("resolution"),
            "cfg_normalize": self._node.get_parameter_value("cfg_normalize"),
            "use_en_prompt": self._node.get_parameter_value("use_en_prompt"),
        }

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        return qwen_latents_to_image_pil(pipe, latents, self.get_height(), self.get_width())
