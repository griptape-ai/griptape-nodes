from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline  # type: ignore[reportMissingImports]
from PIL.Image import Image

from diffusers_nodes_library.common.parameters.diffusion.common.upscale_runtime_parameters import (
    UpscalePipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.common import qwen_latents_to_image_pil
from griptape_nodes.exe_types.node_types import BaseNode


class QwenUpscalePipelineRuntimeParameters(UpscalePipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "true_cfg_scale": self._node.get_parameter_value("true_cfg_scale"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_image_pil(),
            "strength": self._node.get_parameter_value("strength"),
        }

    def latents_to_image_pil(self, pipe: DiffusionPipeline, latents: Any) -> Image:
        tile_size = self.diffuser_tile_size
        return qwen_latents_to_image_pil(pipe, latents, tile_size, tile_size)
