import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.wan.wan_pipeline_type_wan_image_to_video_pipeline_parameters import (
    WanPipelineTypeWanImageToVideoPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.wan.wan_pipeline_type_wan_pipeline_parameters import (
    WanPipelineTypeWanPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.wan.wan_pipeline_type_wan_vace_pipeline_parameters import (
    WanPipelineTypeWanVACEPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.wan.wan_pipeline_type_wan_video_to_video_pipeline_parameters import (
    WanPipelineTypeWanVideoToVideoPipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class WanPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    def pipeline_types(self) -> list[str]:
        return ["WanPipeline", "WanImageToVideoPipeline", "WanVideoToVideoPipeline", "WanVACEPipeline"]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "WanPipeline":
                self._pipeline_type_pipeline_params = WanPipelineTypeWanPipelineParameters(self._node)
            case "WanImageToVideoPipeline":
                self._pipeline_type_pipeline_params = WanPipelineTypeWanImageToVideoPipelineParameters(self._node)
            case "WanVideoToVideoPipeline":
                self._pipeline_type_pipeline_params = WanPipelineTypeWanVideoToVideoPipelineParameters(self._node)
            case "WanVACEPipeline":
                self._pipeline_type_pipeline_params = WanPipelineTypeWanVACEPipelineParameters(self._node)
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
