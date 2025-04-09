from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class MergeKeyValuePair(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add a list of inputs
        self.add_parameter(
            Parameter(
                name="key_value_pair_1",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["dict"],
                tooltip="Key/Value pair inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="key_value_pair_2",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["dict"],
                tooltip="Key/Value pair inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="key_value_pair_3",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["dict"],
                tooltip="Key/Value pair inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="key_value_pair_4",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["dict"],
                tooltip="Key/Value pair inputs to merge together.",
            )
        )

        # Add output parameter for the merged key_value_pair
        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value="",
                tooltip="The merged key value pair result.",
            )
        )

    def process(self) -> None:
        # Get the list of input kvps
        input_1 = self.parameter_values.get("key_value_pair_1", None)
        input_2 = self.parameter_values.get("key_value_pair_2", None)
        input_3 = self.parameter_values.get("key_value_pair_3", None)
        input_4 = self.parameter_values.get("key_value_pair_4", None)

        # Create a list of input texts if they aren't none
        input_dicts = [input_1, input_2, input_3, input_4]
        # Filter out None values from the list
        input_dicts = [text for text in input_dicts if text is not None]

        # Join all the kvps in to a single dict
        merged_dict = {}
        for input_dict in input_dicts:
            if isinstance(input_dict, dict):
                merged_dict.update(input_dict)
        # Set the output
        self.parameter_output_values["output"] = merged_dict
