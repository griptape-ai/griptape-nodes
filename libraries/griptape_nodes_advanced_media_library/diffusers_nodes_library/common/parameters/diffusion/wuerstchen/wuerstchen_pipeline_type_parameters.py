import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.wuerstchen.wuerstchen_pipeline_type_wuerstchen_pipeline_parameters import (
    WuerstchenPipelineTypeWuerstchenPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    def pipeline_types(self) -> list[str]:
        return ["WuerstchenCombinedPipeline"]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "WuerstchenCombinedPipeline":
                self._pipeline_type_pipeline_params = WuerstchenPipelineTypeWuerstchenPipelineParameters(self._node)
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
