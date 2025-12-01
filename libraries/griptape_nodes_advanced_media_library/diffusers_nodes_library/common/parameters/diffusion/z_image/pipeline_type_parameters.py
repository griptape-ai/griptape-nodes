import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.z_image.z_image_parameters import (
    ZImagePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


ZImagePipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "ZImagePipeline": ZImagePipelineParameters,
}


class ZImagePipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return ZImagePipelineTypeDict
