from diffusers_nodes_library.common.parameters.diffusion.qwen.qwen_pipeline_type_qwen_img2_img_pipeline_parameters import (
    QwenPipelineTypeQwenImg2ImgPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode


class QwenPipelineTypeQwenUpscalePipelineParameters(QwenPipelineTypeQwenImg2ImgPipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    @property
    def pipeline_name(self) -> str:
        return "QwenImageUpscalePipeline"
