import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.ltx2.img2vid_parameters import (
    LTX2ImageToVideoPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.ltx2.text2vid_parameters import (
    LTX2TextToVideoPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


LTX2PipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "LTXTextToVideoPipeline": LTX2TextToVideoPipelineParameters,
    "LTXImageToVideoPipeline": LTX2ImageToVideoPipelineParameters,
}


class LTX2PipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return LTX2PipelineTypeDict
