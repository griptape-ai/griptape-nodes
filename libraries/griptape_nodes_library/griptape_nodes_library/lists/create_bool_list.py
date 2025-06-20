from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


class CreateBoolList(ControlNode):
    """CreateBoolList Node that creates a list with boolean items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = ParameterList(
            name="items",
            tooltip="List of boolean items to add to",
            input_types=["bool"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.items_list)
        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if "items_" in parameter.name:
            list_values = self.get_parameter_value("items")

            self.parameter_output_values["output"] = list_values
            self.publish_update_to_parameter("output", list_values)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        self.parameter_output_values["output"] = list_values
