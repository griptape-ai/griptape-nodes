import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.marigold.marigold_depth_parameters import (
    MarigoldDepthPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.marigold.marigold_intrinsics_parameters import (
    MarigoldIntrinsicsPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.marigold.marigold_normals_parameters import (
    MarigoldNormalsPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


MarigoldPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "MarigoldDepthPipeline": MarigoldDepthPipelineParameters,
    "MarigoldNormalsPipeline": MarigoldNormalsPipelineParameters,
    "MarigoldIntrinsicsPipeline": MarigoldIntrinsicsPipelineParameters,
}


class MarigoldPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return MarigoldPipelineTypeDict
