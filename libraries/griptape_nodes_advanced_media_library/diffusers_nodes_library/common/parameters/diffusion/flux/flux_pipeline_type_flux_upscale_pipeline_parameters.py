from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_img2_img_pipeline_parameters import (
    FluxPipelineTypeFluxImg2ImgPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode


class FluxPipelineTypeFluxUpscalePipelineParameters(FluxPipelineTypeFluxImg2ImgPipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    @property
    def pipeline_name(self) -> str:
        return "FluxUpscalePipeline"
