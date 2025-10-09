import logging

from diffusers_nodes_library.common.parameters.diffusion.allegro.allegro_parameters import (
    AllegroPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


AllegroPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "AllegroPipeline": AllegroPipelineParameters
}


class AllegroPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return AllegroPipelineTypeDict
