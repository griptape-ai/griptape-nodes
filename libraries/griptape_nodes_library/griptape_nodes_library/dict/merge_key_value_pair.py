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
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value="",
                tooltip="The merged key value pair result.",
                ui_options={"hide_property": True},
            )
        )

    def get_kv_pairs(self) -> list:
        kv_pairs = self.get_parameter_value("KeyValuePairs")
        if kv_pairs:
            if not isinstance(kv_pairs, list):
                kv_pairs = [kv_pairs]
            return kv_pairs
        return []

    def _merge_kv_pairs(self) -> None:
        """Merge all key-value pairs into a single dictionary."""
        input_dicts = self.get_kv_pairs()

        merged_dict = {}
        for input_dict in input_dicts:
            if isinstance(input_dict, dict):
                merged_dict.update(input_dict)

        self.parameter_output_values["output"] = merged_dict

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "KeyValuePairs":
            self._merge_kv_pairs()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        self._merge_kv_pairs()
