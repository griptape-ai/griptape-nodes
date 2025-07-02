from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class GetListContainsItem(ControlNode):
    """GetListContainsItem Node that that checks if a list contains an item."""

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
            tooltip="Item to check if the list contains",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.item)

        self.contains_item = Parameter(
            name="contains_item",
            tooltip="Output if the list contains the item",
            output_type="bool",
            default_value=True,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.contains_item)

    def _contains_item(self) -> bool:
        list_items = self.get_parameter_value("items")
        item = self.get_parameter_value("item")
        if not item or not list_items:
            return False
        return item in list_items

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "items":
            contains_item = self._contains_item()
            self.parameter_output_values["contains_item"] = contains_item
            self.publish_update_to_parameter("contains_item", contains_item)
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            contains_item = self._contains_item()
            self.parameter_output_values["contains_item"] = contains_item
            self.publish_update_to_parameter("contains_item", contains_item)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            self.parameter_output_values["contains_item"] = False
            self.publish_update_to_parameter("contains_item", False)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        # Get the list of items from the input parameter
        contains_item = self._contains_item()

        self.parameter_output_values["contains_item"] = contains_item
