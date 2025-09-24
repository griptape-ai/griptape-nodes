import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.allegro.allegro_pipeline_type_allegro_pipeline_parameters import (
    AllegroPipelineTypeAllegroPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters

    @property
    def pipeline_types(self) -> list[str]:
        return ["AllegroPipeline"]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "AllegroPipeline":
                self._pipeline_type_pipeline_params = AllegroPipelineTypeAllegroPipelineParameters(self._node)
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
