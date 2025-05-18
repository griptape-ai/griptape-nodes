from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


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

        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value="",
                tooltip="The merged key value pair result.",
            )
        )

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if "KeyValuePair" in target_parameter.name:
            self.set_parameter_to_default_value(target_parameter.name)
            modified_parameters_set.add(target_parameter.name)

        return super().after_incoming_connection_removed(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def get_kv_pairs(self) -> list:
        kv_pairs = self.get_parameter_value("KeyValuePairs")
        if kv_pairs:
            if not isinstance(kv_pairs, list):
                kv_pairs = [kv_pairs]
            return kv_pairs
        return []

    def process(self) -> None:
        input_dicts = self.get_kv_pairs()

        merged_dict = {}
        for input_dict in input_dicts:
            if isinstance(input_dict, dict):
                merged_dict.update(input_dict)

        self.parameter_output_values["output"] = merged_dict
