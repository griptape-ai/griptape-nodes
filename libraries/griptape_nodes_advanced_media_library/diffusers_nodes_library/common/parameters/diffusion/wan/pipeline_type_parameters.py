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
from griptape_nodes.exe_types.node_types import BaseNode

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
                self._pipeline_type_pipeline_params = WanPipelineParameters(self._node)
            case "WanImageToVideoPipeline":
                self._pipeline_type_pipeline_params = WanImageToVideoPipelineParameters(self._node)
            case "WanVideoToVideoPipeline":
                self._pipeline_type_pipeline_params = WanVideoToVideoPipelineParameters(self._node)
            case "WanVACEPipeline":
                self._pipeline_type_pipeline_params = WanVacePipelineParameters(self._node)
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
