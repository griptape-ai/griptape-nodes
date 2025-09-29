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
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters

    @property
    def pipeline_types(self) -> list[str]:
        return [
            "FluxPipeline",
            "FluxFillPipeline",
            "FluxKontextPipeline",
            "FluxImg2ImgPipeline",
            "FluxControlNetPipeline",
            "FluxUpscalePipeline",
        ]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "FluxPipeline":
                self._pipeline_type_pipeline_params = FluxPipelineParameters(self._node)
            case "FluxFillPipeline":
                self._pipeline_type_pipeline_params = FluxFillPipelineParameters(self._node)
            case "FluxKontextPipeline":
                self._pipeline_type_pipeline_params = FluxKontextPipelineParameters(self._node)
            case "FluxImg2ImgPipeline":
                self._pipeline_type_pipeline_params = FluxImg2ImgPipelineParameters(self._node)
            case "FluxControlNetPipeline":
                self._pipeline_type_pipeline_params = FluxControlNetPipelineParameters(self._node)
            case "FluxUpscalePipeline":
                self._pipeline_type_pipeline_params = FluxUpscalePipelineParameters(self._node)
            case _:
                msg = f"Unsupported pipeline type: {pipeline_type}"
                logger.error(msg)
                raise ValueError(msg)

    @property
    def pipeline_type_pipeline_params(self) -> DiffusionPipelineTypePipelineParameters:
        if self._pipeline_type_pipeline_params is None:
            msg = "Pipeline type builder parameters not initialized. Ensure provider parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._pipeline_type_pipeline_params
