import logging

from diffusers_nodes_library.common.parameters.diffusion.amused.amused_parameters import (
    AmusedPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.img2img_parameters import (
    AmusedImg2ImgPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.amused.inpaint_parameters import (
    AmusedInpaintPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
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
                self._pipeline_type_pipeline_params = AmusedPipelineParameters(self._node)
            case "AmusedImg2ImgPipeline":
                self._pipeline_type_pipeline_params = AmusedImg2ImgPipelineParameters(self._node)
            case "AmusedInpaintPipeline":
                self._pipeline_type_pipeline_params = AmusedInpaintPipelineParameters(self._node)
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
