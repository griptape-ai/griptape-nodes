import logging

from diffusers_nodes_library.common.parameters.diffusion.amused.amused_parameters import (
    AmusedPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.img2img_parameters import (
    AmusedImg2ImgPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.inpaint_parameters import (
    AmusedInpaintPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


AmusedPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "AmusedPipeline": AmusedPipelineParameters,
    "AmusedImg2ImgPipeline": AmusedImg2ImgPipelineParameters,
    "AmusedInpaintPipeline": AmusedInpaintPipelineParameters,
}


class AmusedPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return AmusedPipelineTypeDict
