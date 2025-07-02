from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options


class AddToList(ControlNode):
    """AddToList Node that takes a list, an item, and an optional index.

    It adds the item to the list at the specified index, or at the end of the list if no index is provided.
    """

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

        self.item = Parameter(
            name="item",
            tooltip="Item to add to the list",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.item)

        self.position = Parameter(
            name="position",
            tooltip="Position to add the value to the list",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="end",
        )
        self.add_parameter(self.position)
        self.position.add_trait(Options(choices=["start", "end", "index"]))
        self.index = Parameter(
            name="index",
            tooltip="Index to add the value to the list",
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
        if parameter.name == "position":
            if value in {"start", "end"}:
                self.hide_parameter_by_name("index")
            elif value == "index":
                self.show_parameter_by_name("index")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if not list_values or not isinstance(list_values, list):
            return

        item = self.get_parameter_value("item")
        if not item:
            return

        position = self.get_parameter_value("position")
        if position == "start":
            index = 0
        elif position == "end":
            index = len(list_values)
        else:
            index = self.get_parameter_value("index")

        new_list = deepcopy(list_values)
        new_list.insert(index, item)

        self.parameter_output_values["output"] = new_list
