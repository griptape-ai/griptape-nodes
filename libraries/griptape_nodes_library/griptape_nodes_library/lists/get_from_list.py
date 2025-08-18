from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes.traits.options import Options


class GetFromList(ControlNode):
    """GetFromList Node that gets an item at a specified index from a list."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to get an item from",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        self.position = Parameter(
            name="position",
            tooltip="Position to get the value from the list",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="index",
        )
        self.add_parameter(self.position)
        self.position.add_trait(Options(choices=["index", "start", "end"]))

        self.index = Parameter(
            name="index",
            tooltip="Index to get the item from",
            input_types=["int", "float"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.index)

        self.item = Parameter(
            name="item",
            tooltip="Output the item at the specified index",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.item)

    def _get_item(self) -> Any:
        list_items = self.get_parameter_value("items")
        if not list_items:
            return None

        position = self.get_parameter_value("position")
        if position == "start":
            index = 0
        elif position == "end":
            index = len(list_items) - 1
        else:
            index = self.get_parameter_value("index")
            if index is None:
                return None

        try:
            # Convert index to integer, handling both int and float inputs
            index = int(index)
            return list_items[index]
        except (IndexError, TypeError, ValueError):
            return None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "position":
            if value in {"start", "end"}:
                self.hide_parameter_by_name("index")
            elif value == "index":
                self.show_parameter_by_name("index")
        if parameter.name in ["items", "index", "position"]:
            item = self._get_item()
            self.parameter_output_values["item"] = item
            self.publish_update_to_parameter("item", item)
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name in ["items", "index"]:
            item = self._get_item()
            self.parameter_output_values["item"] = item
            self.publish_update_to_parameter("item", item)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name in ["items", "index"]:
            self.parameter_output_values["item"] = None
            self.publish_update_to_parameter("item", None)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        item = self._get_item()
        self.parameter_output_values["item"] = item
