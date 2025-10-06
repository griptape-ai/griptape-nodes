import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.wuerstchen_parameters import (
    WuerstchenPipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


WuerstchenPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "WuerstchenPipeline": WuerstchenPipelineParameters
}


class WuerstchenPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return WuerstchenPipelineTypeDict
