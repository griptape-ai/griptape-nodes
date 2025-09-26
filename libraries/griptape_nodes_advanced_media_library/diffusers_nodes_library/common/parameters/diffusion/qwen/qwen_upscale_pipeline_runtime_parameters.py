from diffusers_nodes_library.common.parameters.diffusion.common.upscale_pipeline_runtime_parameters import (
    UpscalePipelineRuntimeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode


class QwenUpscalePipelineRuntimeParameters(UpscalePipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        super()._add_input_parameters()

        self._node.hide_parameter_by_name("prompt_2")
        self._node.hide_parameter_by_name("negative_prompt_2")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self._node.get_parameter_value("prompt"),
            "negative_prompt": self._node.get_parameter_value("negative_prompt"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "image": self.get_image_pil(),
            "strength": self._node.get_parameter_value("strength"),
        }
