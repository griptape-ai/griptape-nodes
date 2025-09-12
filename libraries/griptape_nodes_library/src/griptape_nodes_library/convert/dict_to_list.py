from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class DictToList(DataNode):
    """Extract lists of keys and values from a dictionary."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for the input dictionary
        self.add_parameter(
            Parameter(
                name="dict",
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value={},
                tooltip="Dictionary to extract values from",
            )
        )

        # Add keys output parameter
        self.add_parameter(
            Parameter(
                name="keys",
                output_type="list",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=[],
                tooltip="List of dictionary keys",
                ui_options={"hide_property": True},
            )
        )

        # Add values output parameter
        self.add_parameter(
            Parameter(
                name="values",
                output_type="list",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=[],
                tooltip="List of dictionary values",
                ui_options={"hide_property": True},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "dict":
            # Get the input dictionary
            input_dict = self.get_parameter_value("dict")

            # Ensure it's actually a dictionary
            if not isinstance(input_dict, dict):
                input_dict = {}

            # Extract keys and values as lists
            keys_list = list(input_dict.keys())
            values_list = list(input_dict.values())

            # Set output keys
            self.parameter_output_values["keys"] = keys_list
            self.set_parameter_value("keys", keys_list)
            self.show_parameter_by_name("keys")

            # Set output values
            self.parameter_output_values["values"] = values_list
            self.set_parameter_value("values", values_list)
            self.show_parameter_by_name("values")

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by extracting keys and values from the dictionary."""
        self.parameter_output_values["keys"] = self.parameter_values["keys"]
        self.parameter_output_values["values"] = self.parameter_values["values"]
