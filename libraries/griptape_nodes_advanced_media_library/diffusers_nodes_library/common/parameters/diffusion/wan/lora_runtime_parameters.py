import logging

from diffusers_nodes_library.common.parameters.diffusion.runtime_parameters import (
    DiffusionPipelineRuntimeParameters,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WanLoraRuntimeParameters(DiffusionPipelineRuntimeParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)

    def _add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="weight",
                default_value=1.0,
                type="float",
                tooltip="LoRA weight for WAN pipeline",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="loras",
                default_value=1.0,
                type="loras",
                output_type="loras",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="loras",
            )
        )

    def _remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("weight")

    def remove_output_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("loras")

    def _get_pipe_kwargs(self) -> dict:
        return {
            "weight": self.get_weight(),
        }

    def get_weight(self) -> float:
        return float(self._node.get_parameter_value("weight"))

    def set_output_lora(self, lora: dict) -> None:
        self._node.set_parameter_value("loras", lora)
        self._node.parameter_output_values["loras"] = lora
