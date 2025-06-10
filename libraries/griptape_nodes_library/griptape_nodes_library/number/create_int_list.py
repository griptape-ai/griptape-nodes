from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class CreateIntList(ControlNode):
    """CreateIntList Node that creates a list with integer items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = ParameterList(
            name="items",
            tooltip="List of integer items to add to",
            input_types=["int"],
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

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if "items_" in parameter.name:
            list_values = self.get_parameter_value("items")

            # Set Parameter Output Values
            self.parameter_output_values["output"] = list_values

            # # Publish Update to Parameter
            self.publish_update_to_parameter("output", list_values)

            # Add Parameters to Modified Parameters Set
            modified_parameters_set.add("output")

            # Node name
            node_name = self.name

            # Log the value
            logger.debug(f"{node_name}: Set the value to: {list_values}")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        self.parameter_output_values["output"] = list_values
