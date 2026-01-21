import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux2.flux2_klein_parameters import (
    Flux2KleinPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux2.flux2_parameters import (
    Flux2PipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


Flux2PipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "Flux2Pipeline": Flux2PipelineParameters,
    "Flux2KleinPipeline": Flux2KleinPipelineParameters,
}


class Flux2PipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return Flux2PipelineTypeDict
