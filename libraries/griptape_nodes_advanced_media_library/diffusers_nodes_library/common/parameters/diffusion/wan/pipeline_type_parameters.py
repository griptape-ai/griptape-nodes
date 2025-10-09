import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.img2vid_parameters import (
    WanImageToVideoPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.vace_parameters import (
    WanVacePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.vid2vid_parameters import (
    WanVideoToVideoPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.wan_parameters import (
    WanPipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


WanPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "WanPipeline": WanPipelineParameters,
    "WanImageToVideoPipeline": WanImageToVideoPipelineParameters,
    "WanVideoToVideoPipeline": WanVideoToVideoPipelineParameters,
    "WanVacePipeline": WanVacePipelineParameters,
}


class WanPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return WanPipelineTypeDict
