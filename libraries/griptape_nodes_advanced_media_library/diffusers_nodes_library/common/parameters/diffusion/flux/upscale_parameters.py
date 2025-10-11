from diffusers_nodes_library.common.parameters.diffusion.flux.img2img_parameters import (
    FluxImg2ImgPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode


class FluxUpscalePipelineParameters(FluxImg2ImgPipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node, list_all_models=list_all_models)

    @property
    def pipeline_name(self) -> str:
        return "FluxUpscalePipeline"
