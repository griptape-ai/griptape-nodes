import logging

from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.depthcrafter_parameters import (
    DepthCrafterPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


DepthCrafterPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "DepthCrafterVideoDiffusionPipeline": DepthCrafterPipelineParameters
}


class DepthCrafterPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return DepthCrafterPipelineTypeDict
