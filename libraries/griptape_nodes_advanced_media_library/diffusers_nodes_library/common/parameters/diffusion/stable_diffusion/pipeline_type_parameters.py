import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.attend_excite_parameters import (
    StableDiffusionAttendAndExcitePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.diff_edit_parameters import (
    StableDiffusionDiffEditPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.sd3_parameters import (
    StableDiffusion3PipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.sd_parameters import (
    StableDiffusionPipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


StableDiffusionPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "StableDiffusionPipeline": StableDiffusionPipelineParameters,
    "StableDiffusion3Pipeline": StableDiffusion3PipelineParameters,
    "StableDiffusionAttendAndExcitePipeline": StableDiffusionAttendAndExcitePipelineParameters,
    "StableDiffusionDiffEditPipeline": StableDiffusionDiffEditPipelineParameters,
}


class StableDiffusionPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return StableDiffusionPipelineTypeDict
