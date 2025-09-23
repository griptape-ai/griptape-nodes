import logging
from typing import Any

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from diffusers_nodes_library.common.parameters.diffusion.flux.flux_pipeline_runtime_parameters import (
    FluxPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

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

        pipeline_class = value.split("-", 1)[0]
        match pipeline_class:
            case "FluxPipeline":
                self._runtime_parameters = FluxPipelineRuntimeParameters(self._node)
            case _:
                msg = f"Unsupported pipeline type: {pipeline_class}"
                logger.error(msg)
                raise ValueError(msg)

        self._runtime_parameters.add_input_parameters()
        self._runtime_parameters.add_output_parameters()

    @property
    def runtime_parameters(self) -> DiffusionPipelineRuntimeParameters:
        if self._runtime_parameters is None:
            msg = "Runtime parameters not initialized. Ensure pipeline parameter is set."
            logger.error(msg)
            raise ValueError(msg)
        return self._runtime_parameters
