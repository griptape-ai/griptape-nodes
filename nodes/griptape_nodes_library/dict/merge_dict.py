from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class MergeDicts(DataNode):
    """Merge multiple dictionaries, with later dictionaries overwriting values from earlier ones."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of input dictionaries
        self.add_parameter(
            Parameter(
                name="inputs",
                input_types=["list[dict]", "list"],
                type="list[dict]",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=[],
                tooltip="List of dictionaries to merge",
            )
        )

        # Add merged dictionary output parameter
        self.add_parameter(
            Parameter(
                name="merged_dict",
                output_type="dict",
                allowed_modes={ParameterMode.OUTPUT},
                default_value={},
                tooltip="The merged dictionary",
            )
        )

    def process(self) -> None:
        """Process the node by merging all dictionaries from the list."""
        # Get the list of dictionaries
        dict_list = self.parameter_values.get("inputs", [])

        # Ensure it's actually a list
        if not isinstance(dict_list, list):
            dict_list = [dict_list] if dict_list is not None else []

        # Create a result dictionary
        result_dict = {}

        # Merge dictionaries in order, with later ones overwriting earlier ones
        for d in dict_list:
            # Skip None entries
            if d is None:
                continue

            # Ensure the item is a dictionary
            if not isinstance(d, dict):
                continue

            # Update the result dictionary with the current dictionary
            result_dict.update(d)

        # Set output values
        self.parameter_output_values["merged_dict"] = result_dict
        self.parameter_values["merged_dict"] = result_dict  # For get_value compatibility
