import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.stable_diffusion_pipeline_type_stable_diffusion_3_pipeline_parameters import (
    StableDiffusionPipelineTypeStableDiffusion3PipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.stable_diffusion_pipeline_type_stable_diffusion_attend_and_excite_pipeline_parameters import (
    StableDiffusionPipelineTypeStableDiffusionAttendAndExcitePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.stable_diffusion_pipeline_type_stable_diffusion_diff_edit_pipeline_parameters import (
    StableDiffusionPipelineTypeStableDiffusionDiffEditPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.stable_diffusion.stable_diffusion_pipeline_type_stable_diffusion_pipeline_parameters import (
    StableDiffusionPipelineTypeStableDiffusionPipelineParameters,
)

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
                self._pipeline_type_pipeline_params = StableDiffusionPipelineTypeStableDiffusionPipelineParameters(
                    self._node
                )
            case "StableDiffusion3Pipeline":
                self._pipeline_type_pipeline_params = StableDiffusionPipelineTypeStableDiffusion3PipelineParameters(
                    self._node
                )
            case "StableDiffusionAttendAndExcitePipeline":
                self._pipeline_type_pipeline_params = (
                    StableDiffusionPipelineTypeStableDiffusionAttendAndExcitePipelineParameters(self._node)
                )
            case "StableDiffusionDiffEditPipeline":
                self._pipeline_type_pipeline_params = (
                    StableDiffusionPipelineTypeStableDiffusionDiffEditPipelineParameters(self._node)
                )
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
