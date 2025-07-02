from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class GetIndexOfItem(ControlNode):
    """GetIndexOfItem Node that that gets the index of an item in a list."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)
        self.item = Parameter(
            name="item",
            tooltip="Item to get the index of",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.item)

        self.index = Parameter(
            name="index",
            tooltip="Output the index of the item in the list",
            output_type="int",
            default_value=0,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.index)

    def _get_index(self) -> int:
        list_items = self.get_parameter_value("items")
        item = self.get_parameter_value("item")
        if not item or not list_items:
            return -1
        return list_items.index(item)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "items":
            index = self._get_index()
            self.parameter_output_values["index"] = index
            self.publish_update_to_parameter("index", index)
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            index = self._get_index()
            self.parameter_output_values["index"] = index
            self.publish_update_to_parameter("index", index)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            self.parameter_output_values["index"] = -1
            self.publish_update_to_parameter("index", -1)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        # Get the list of items from the input parameter
        index = self._get_index()

        self.parameter_output_values["index"] = index
