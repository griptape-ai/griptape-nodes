import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.controlnet_parameters import (
    FluxControlNetPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.fill_parameters import (
    FluxFillPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_parameters import (
    FluxPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.img2img_parameters import (
    FluxImg2ImgPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.kontext_parameters import (
    FluxKontextPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.upscale_parameters import (
    FluxUpscalePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


FluxPipelineTypeDict: dict[str, type[DiffusionPipelineTypePipelineParameters]] = {
    "FluxPipeline": FluxPipelineParameters,
    "FluxFillPipeline": FluxFillPipelineParameters,
    "FluxKontextPipeline": FluxKontextPipelineParameters,
    "FluxImg2ImgPipeline": FluxImg2ImgPipelineParameters,
    "FluxControlNetPipeline": FluxControlNetPipelineParameters,
    "FluxUpscalePipeline": FluxUpscalePipelineParameters,
}


class FluxPipelineTypeParameters(DiffusionPipelineTypeParameters):
    @property
    def pipeline_type_dict(self) -> dict[str, type[DiffusionPipelineTypePipelineParameters]]:
        return FluxPipelineTypeDict
