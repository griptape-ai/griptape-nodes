import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.attend_excite_parameters import (
    StableDiffusionAttendAndExcitePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.diff_edit_parameters import (
    StableDiffusionDiffEditPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.sd3_parameters import (
    StableDiffusion3PipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.sd_parameters import (
    StableDiffusionPipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class StableDiffusionPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters
        self.set_pipeline_type_pipeline_params(self.pipeline_types[0])

    @property
    def pipeline_types(self) -> list[str]:
        return [
            "StableDiffusionPipeline",
            "StableDiffusion3Pipeline",
            "StableDiffusionAttendAndExcitePipeline",
            "StableDiffusionDiffEditPipeline",
        ]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "StableDiffusionPipeline":
                self._pipeline_type_pipeline_params = StableDiffusionPipelineParameters(self._node)
            case "StableDiffusion3Pipeline":
                self._pipeline_type_pipeline_params = StableDiffusion3PipelineParameters(self._node)
            case "StableDiffusionAttendAndExcitePipeline":
                self._pipeline_type_pipeline_params = StableDiffusionAttendAndExcitePipelineParameters(self._node)
            case "StableDiffusionDiffEditPipeline":
                self._pipeline_type_pipeline_params = StableDiffusionDiffEditPipelineParameters(self._node)
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
