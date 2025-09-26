import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.qwen.qwen_pipeline_type_qwen_img2_img_pipeline_parameters import (
    QwenPipelineTypeQwenImg2ImgPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.qwen.qwen_pipeline_type_qwen_pipeline_parameters import (
    QwenPipelineTypeQwenPipelineParameters,
)
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.qwen.qwen_pipeline_type_qwen_upscale_pipeline_parameters import (
    QwenPipelineTypeQwenUpscalePipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class QwenPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters

    @property
    def pipeline_types(self) -> list[str]:
        return [
            "QwenPipeline",
            "QwenImg2ImgPipeline",
            "QwenUpscalePipeline",
        ]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "QwenPipeline":
                self._pipeline_type_pipeline_params = QwenPipelineTypeQwenPipelineParameters(self._node)
            case "QwenImg2ImgPipeline":
                self._pipeline_type_pipeline_params = QwenPipelineTypeQwenImg2ImgPipelineParameters(self._node)
            case "QwenUpscalePipeline":
                self._pipeline_type_pipeline_params = QwenPipelineTypeQwenUpscalePipelineParameters(self._node)
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
