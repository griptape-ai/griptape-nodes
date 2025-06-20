from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class GetListLength(ControlNode):
    """GetListLength Node that that gets the length of a list."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)
        self.length = Parameter(
            name="length",
            tooltip="Output length of the list",
            output_type="int",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.length)

    def _get_length(self) -> int:
        list_items = self.get_parameter_value("items")
        if list_items:
            return len(list_items)
        return 0

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "items":
            length = self._get_length()
            self.parameter_output_values["length"] = length
            self.publish_update_to_parameter("length", length)
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            length = self._get_length()
            self.parameter_output_values["length"] = length
            self.publish_update_to_parameter("length", length)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            self.parameter_output_values["length"] = 0
            self.publish_update_to_parameter("length", 0)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        # Get the list of items from the input parameter
        length = self._get_length()

        self.parameter_output_values["length"] = length
