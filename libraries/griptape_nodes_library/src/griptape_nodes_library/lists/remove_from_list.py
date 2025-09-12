from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options


class RemoveFromList(ControlNode):
    """RemoveFromList Node that takes a list and removes an item based on specified criteria."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to add to",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        self.remove_item_by = Parameter(
            name="remove_item_by",
            tooltip="How to remove the item from the list",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="item",
        )
        self.add_parameter(self.remove_item_by)
        self.remove_item_by.add_trait(Options(choices=["first", "last", "index", "item"]))
        self.value = Parameter(
            name="item",
            tooltip="Item to remove from the list",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.value)
        self.index = Parameter(
            name="index",
            tooltip="Index to remove the item from the list",
            type="int",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"hide": True},
        )
        self.add_parameter(self.index)

        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "remove_item_by":
            if value in {"first", "last"}:
                self.hide_parameter_by_name("index")
                self.hide_parameter_by_name("item")
            elif value == "index":
                self.show_parameter_by_name("index")
                self.hide_parameter_by_name("item")
            elif value == "item":
                self.show_parameter_by_name("item")
                self.hide_parameter_by_name("index")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if not list_values or not isinstance(list_values, list):
            return
        remove_item_by = self.get_parameter_value("remove_item_by")
        index = 0  # Initialize index with a default value
        if remove_item_by == "first":
            index = 0
        elif remove_item_by == "last":
            index = len(list_values) - 1
        elif remove_item_by == "index":
            index = self.get_parameter_value("index")
        elif remove_item_by == "item":
            index = list_values.index(self.get_parameter_value("item"))

        new_list = deepcopy(list_values)
        new_list.pop(index)
        self.parameter_output_values["output"] = new_list
