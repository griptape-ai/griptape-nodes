import logging

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_parameters import (
    DiffusionPipelineTypeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.img2img_parameters import (
    QwenImg2ImgPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.qwen_parameters import (
    QwenPipelineParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.qwen.upscale_parameters import (
    QwenUpscalePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class QwenPipelineTypeParameters(DiffusionPipelineTypeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._pipeline_type_pipeline_params: DiffusionPipelineTypePipelineParameters

    @property
    def pipeline_types(self) -> list[str]:
        return [
            "QwenImagePipeline",
            "QwenImageImg2ImgPipeline",
            "QwenImageUpscalePipeline",
        ]

    def set_pipeline_type_pipeline_params(self, pipeline_type: str) -> None:
        match pipeline_type:
            case "QwenImagePipeline":
                self._pipeline_type_pipeline_params = QwenPipelineParameters(self._node)
            case "QwenImageImg2ImgPipeline":
                self._pipeline_type_pipeline_params = QwenImg2ImgPipelineParameters(self._node)
            case "QwenImageUpscalePipeline":
                self._pipeline_type_pipeline_params = QwenUpscalePipelineParameters(self._node)
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
