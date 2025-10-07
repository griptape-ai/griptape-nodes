from diffusers_nodes_library.common.parameters.diffusion.qwen.img2img_parameters import (
    QwenImg2ImgPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode


class QwenUpscalePipelineParameters(QwenImg2ImgPipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node, list_all_models=list_all_models)

    @property
    def pipeline_name(self) -> str:
        return "QwenImageUpscalePipeline"
