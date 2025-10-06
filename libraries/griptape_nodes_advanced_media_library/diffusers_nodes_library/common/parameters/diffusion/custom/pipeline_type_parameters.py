import logging

from diffusers_nodes_library.common.parameters.diffusion.allegro.pipeline_type_parameters import AllegroPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.amused.pipeline_type_parameters import AmusedPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.audioldm.pipeline_type_parameters import (
    AudioldmPipelineTypeDict,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.pipeline_type_parameters import FluxPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.pipeline_type_parameters import QwenPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.pipeline_type_parameters import (
    StableDiffusionPipelineTypeDict,
)
from diffusers_nodes_library.common.parameters.diffusion.wan.pipeline_type_parameters import WanPipelineTypeDict
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.pipeline_type_parameters import (
    WuerstchenPipelineTypeDict,
)

logger = logging.getLogger("diffusers_nodes_library")


AllPipelineTypes: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    **AllegroPipelineTypeDict,
    **AmusedPipelineTypeDict,
    **AudioldmPipelineTypeDict,
    **FluxPipelineTypeDict,
    **QwenPipelineTypeDict,
    **StableDiffusionPipelineTypeDict,
    **WanPipelineTypeDict,
    **WuerstchenPipelineTypeDict,
}


class CustomPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return AllPipelineTypes
