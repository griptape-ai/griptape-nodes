import logging

from diffusers_nodes_library.common.parameters.diffusion.audioldm.audioldm_parameters import (
    AudioldmPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


AudioldmPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "AudioLDMPipeline": AudioldmPipelineParameters
}


class AudioldmPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return AudioldmPipelineTypeDict
