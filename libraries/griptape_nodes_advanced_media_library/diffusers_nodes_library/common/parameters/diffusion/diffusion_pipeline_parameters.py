import logging
from typing import Any

from diffusers.pipelines.pipeline_utils import DiffusionPipeline
from diffusers.pipelines.flux.pipeline_flux import FluxPipeline
from diffusers.pipelines.flux.pipeline_flux_fill import FluxFillPipeline

from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_runtime_parameters import FluxPipelineRuntimeParameters
from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_runtime_parameters import DiffusionPipelineRuntimeParameters
from diffusers_nodes_library.common.utils.huggingface_utils import model_cache

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.core_types import Parameter



logger = logging.getLogger("diffusers_nodes_library")


class DiffusionPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node: BaseNode = node
        self._runtime_parameters: DiffusionPipelineRuntimeParameters | None = None

    def add_input_parameters(self) -> None:
        # TODO: Implement with Resource Manager integration - https://github.com/griptape-ai/griptape-nodes/issues/2237
        pass

    def test(self) -> None:
        if isinstance(self.pipeline, FluxPipeline):
            self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
        # elif isinstance(self.pipeline, FluxFillPipeline):
        #     self._runtime_parameters = FluxFillPipelineRuntimeParameters(self._node)
        else:
            raise ValueError(f"Unsupported pipeline type: {type(self.pipeline)}")

        self._runtime_parameters.add_input_parameters()
        self._runtime_parameters.add_output_parameters()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "diffusion_pipeline":
            return
        
        if isinstance(self.pipeline, FluxPipeline):
            self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
        # elif isinstance(self.pipeline, FluxFillPipeline):
        #     self._runtime_parameters = FluxFillPipelineRuntimeParameters(self._node)
        else:
            raise ValueError(f"Unsupported pipeline type: {type(self.pipeline)}")

        self._runtime_parameters.add_input_parameters()
        self._runtime_parameters.add_output_parameters()

    @property
    def pipeline(self) -> DiffusionPipeline:
        # TODO: Implement with Resource Manager integration - https://github.com/griptape-ai/griptape-nodes/issues/2237
        return model_cache.pipeline
    
    @property
    def runtime_parameters(self) -> DiffusionPipelineRuntimeParameters:
        if self._runtime_parameters is None:
            raise ValueError("Runtime parameters not initialized. Ensure diffusion_pipeline parameter is set.")
        return self._runtime_parameters
