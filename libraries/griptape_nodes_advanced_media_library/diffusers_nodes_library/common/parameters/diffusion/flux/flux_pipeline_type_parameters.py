import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_control_net_pipeline_parameters import (
    FluxPipelineTypeFluxControlNetPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_fill_pipeline_parameters import (
    FluxPipelineTypeFluxFillPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_img2_img_pipeline_parameters import (
    FluxPipelineTypeFluxImg2ImgPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_kontext_pipeline_parameters import (
    FluxPipelineTypeFluxKontextPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_upscale_pipeline_parameters import (
    FluxPipelineTypeFluxUpscalePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_type_flux_pipeline_parameters import (
    FluxPipelineTypeFluxPipelineParameters,
)

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
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxPipelineParameters(self._node)
            case "FluxFillPipeline":
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxFillPipelineParameters(self._node)
            case "FluxKontextPipeline":
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxKontextPipelineParameters(self._node)
            case "FluxImg2ImgPipeline":
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxImg2ImgPipelineParameters(self._node)
            case "FluxControlNetPipeline":
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxControlNetPipelineParameters(self._node)
            case "FluxUpscalePipeline":
                self._pipeline_type_pipeline_params = FluxPipelineTypeFluxUpscalePipelineParameters(self._node)
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
