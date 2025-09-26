import logging
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_controlnet_pipeline_runtime_parameters import (
    FluxControlNetPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_fill_pipeline_runtime_parameters import (
    FluxFillPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_img2img_pipeline_runtime_parameters import (
    FluxImg2ImgPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_kontext_pipeline_runtime_parameters import (
    FluxKontextPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_runtime_parameters import (
    FluxPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from libraries.griptape_nodes_advanced_media_library.diffusers_nodes_library.common.parameters.diffusion.flux.flux_upscale_pipeline_runtime_parameters import (
    FluxUpscalePipelineRuntimeParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node: BaseNode = node
        self._runtime_parameters: DiffusionPipelineRuntimeParameters
        self.set_runtime_parameters("FluxPipeline")

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                type="Pipeline Config",
                tooltip="🤗 Diffusion Pipeline",
                allowed_modes={ParameterMode.INPUT},
            )
        )

    def set_runtime_parameters(self, pipeline_class: str) -> None:
        match pipeline_class:
            case "FluxPipeline":
                self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
            case "FluxFillPipeline":
                self._runtime_parameters = FluxFillPipelineRuntimeParameters(self._node)
            case "FluxControlNetPipeline":
                self._runtime_parameters = FluxControlNetPipelineRuntimeParameters(self._node)
            case "FluxKontextPipeline":
                self._runtime_parameters = FluxKontextPipelineRuntimeParameters(self._node)
            case "FluxImg2ImgPipeline":
                self._runtime_parameters = FluxImg2ImgPipelineRuntimeParameters(self._node)
            case "FluxUpscalePipeline":
                self._runtime_parameters = FluxUpscalePipelineRuntimeParameters(self._node)
            case _:
                msg = f"Unsupported pipeline class: {pipeline_class}"
                logger.error(msg)
                raise ValueError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "pipeline":
            return

        pipeline_class = value.split("-", 1)[0]
        self.set_runtime_parameters(pipeline_class)

        self.runtime_parameters.add_input_parameters()
        self.runtime_parameters.add_output_parameters()

    @property
    def runtime_parameters(self) -> DiffusionPipelineRuntimeParameters:
        if self._runtime_parameters is None:
            msg = "Runtime parameters not initialized. Ensure pipeline parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._runtime_parameters
