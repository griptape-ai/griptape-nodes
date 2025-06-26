from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class DictValues(DataNode):
    """Extract a list of values from a dictionary."""

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

        # Add list output parameter
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

    def process(self) -> None:
        """Process the node by extracting values from the dictionary."""
        # Get the input dictionary
        input_dict = self.parameter_values.get("dict", {})

        # Ensure it's actually a dictionary
        if not isinstance(input_dict, dict):
            input_dict = {}

        # Extract values as a list
        values_list = list(input_dict.values())

        # Set output values
        self.parameter_output_values["values"] = values_list
        self.parameter_values["values"] = values_list  # For get_value compatibility
