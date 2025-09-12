from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options


class ReplaceInList(ControlNode):
    """ReplaceInList Node that takes a list and replaces an item either by matching the item or by index.

    It replaces the item in the list with a new item and outputs the modified list.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to replace from",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        self.replace_by = Parameter(
            name="replace_by",
            tooltip="How to identify the item to replace",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="item",
        )
        self.add_parameter(self.replace_by)
        self.replace_by.add_trait(Options(choices=["item", "index"]))

        self.item_to_replace = Parameter(
            name="item_to_replace",
            tooltip="Item to replace in the list",
            input_types=["any"],
            default_value=None,
            allowed_modes={ParameterMode.INPUT},
            ui_options={"hide": False},
        )
        self.add_parameter(self.item_to_replace)

        self.index_to_replace = Parameter(
            name="index_to_replace",
            tooltip="Index of item to replace in the list",
            input_types=["int"],
            default_value=0,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"hide": True},
        )
        self.add_parameter(self.index_to_replace)

        self.new_item = Parameter(
            name="new_item",
            tooltip="New item to replace with",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.new_item)

        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "replace_by":
            if value == "item":
                self.show_parameter_by_name("item_to_replace")
                self.hide_parameter_by_name("index_to_replace")
            elif value == "index":
                self.hide_parameter_by_name("item_to_replace")
                self.show_parameter_by_name("index_to_replace")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if not list_values or not isinstance(list_values, list):
            return

        new_item = self.get_parameter_value("new_item")
        if not new_item:
            return

        replace_by = self.get_parameter_value("replace_by")
        new_list = deepcopy(list_values)

        if replace_by == "item":
            item_to_replace = self.get_parameter_value("item_to_replace")
            if item_to_replace is None:
                return
            try:
                index = new_list.index(item_to_replace)
                new_list[index] = new_item
            except ValueError:
                return
        else:  # replace_by == "index"
            index = self.get_parameter_value("index_to_replace")
            if index is None or not isinstance(index, int):
                return
            if 0 <= index < len(new_list):
                new_list[index] = new_item
            else:
                return
        self.parameter_output_values["output"] = new_list
