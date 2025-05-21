from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class FluxLoraParameters:
    def __init__(self, node: BaseNode):
        self._node = node

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="weight",
                default_value=1.0,
                input_types=["float"],
                type="float",
                tooltip="prompt",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
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

    def get_weight(self) -> float:
        return float(self._node.get_parameter_value("weight"))

    def set_output_lora(self, lora: dict) -> None:
        self._node.set_parameter_value("loras", lora)
        self._node.parameter_output_values["loras"] = lora
