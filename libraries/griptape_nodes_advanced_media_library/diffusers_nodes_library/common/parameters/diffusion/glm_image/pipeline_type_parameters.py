import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.glm_image.glm_image_parameters import (
    GlmImagePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


GlmImagePipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "GlmImagePipeline": GlmImagePipelineParameters,
}


class GlmImagePipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return GlmImagePipelineTypeDict
