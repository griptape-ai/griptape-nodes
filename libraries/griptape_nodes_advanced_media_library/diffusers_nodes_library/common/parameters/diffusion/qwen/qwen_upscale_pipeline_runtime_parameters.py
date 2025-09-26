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
