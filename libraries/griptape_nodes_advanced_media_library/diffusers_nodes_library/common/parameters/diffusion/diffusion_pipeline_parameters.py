from asyncio.windows_utils import pipe
import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.flux.pipeline_flux import FluxPipeline
from diffusers.pipelines.flux.pipeline_flux_fill import FluxFillPipeline

from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_runtime_parameters import FluxPipelineRuntimeParameters
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_runtime_parameters import DiffusionPipelineRuntimeParameters
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode



logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node: BaseNode = node
        self._runtime_parameters: DiffusionPipelineRuntimeParameters | None = None

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="pipeline",
                type="Pipeline Config",
                tooltip="🤗 Diffusion Pipeline",
                allowed_modes={ParameterMode.INPUT},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "pipeline":
            return
        
        pipeline_class = value.split('-', 1)[0]
        match pipeline_class:
            case "FluxPipeline":
                self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
            # case "FluxFillPipeline":
            #     self._runtime_parameters = FluxFillPipelineRuntimeParameters(self._node)
            case _:
                raise ValueError(f"Unsupported pipeline type: {pipeline_class}")

        self._runtime_parameters.add_input_parameters()
        self._runtime_parameters.add_output_parameters()
    
    @property
    def runtime_parameters(self) -> DiffusionPipelineRuntimeParameters:
        if self._runtime_parameters is None:
            raise ValueError("Runtime parameters not initialized. Ensure pipeline parameter is set.")
        return self._runtime_parameters
