from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class MergeKeyValuePairs(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterList(
                name="KeyValuePairs",
                input_types=["dict"],
                default_value=None,
                tooltip="Key Value Pair",
                allowed_modes={ParameterMode.INPUT},
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

    def get_kv_pairs(self) -> list:
        kv_pairs = self.get_parameter_value("KeyValuePairs")
        if kv_pairs:
            if not isinstance(kv_pairs, list):
                kv_pairs = [kv_pairs]
            return kv_pairs
        return []

    def process(self) -> None:
        # Create a list of input texts if they aren't none
        input_dicts = self.get_kv_pairs()

        # Filter out None values from the list
        # input_dicts = [text for text in input_dicts if text is not None]

        # Join all the kvps in to a single dict
        merged_dict = {}
        for input_dict in input_dicts:
            if isinstance(input_dict, dict):
                merged_dict.update(input_dict)
        # Set the output
        self.parameter_output_values["output"] = merged_dict
