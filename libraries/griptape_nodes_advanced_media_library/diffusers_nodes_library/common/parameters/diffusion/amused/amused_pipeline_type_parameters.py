import logging

from griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.amused.amused_pipeline_type_amused_img2_img_pipeline_parameters import (
    AmusedPipelineTypeAmusedImg2ImgPipelineParameters,
)
from griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.amused.amused_pipeline_type_amused_inpaint_pipeline_parameters import (
    AmusedPipelineTypeAmusedInpaintPipelineParameters,
)
from griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.amused.amused_pipeline_type_amused_pipeline_parameters import (
    AmusedPipelineTypeAmusedPipelineParameters,
)
from griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    def pipeline_types(self) -> list[str]:
        return ["AmusedPipeline", "AmusedImg2ImgPipeline", "AmusedInpaintPipeline"]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "AmusedPipeline":
                self._pipeline_type_pipeline_params = AmusedPipelineTypeAmusedPipelineParameters(self._node)
            case "AmusedImg2ImgPipeline":
                self._pipeline_type_pipeline_params = AmusedPipelineTypeAmusedImg2ImgPipelineParameters(self._node)
            case "AmusedInpaintPipeline":
                self._pipeline_type_pipeline_params = AmusedPipelineTypeAmusedInpaintPipelineParameters(self._node)
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
