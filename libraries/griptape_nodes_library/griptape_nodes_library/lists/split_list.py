from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options


class SplitList(ControlNode):
    """SplitList Node that takes a list and splits it either by index or by item value.

    When splitting by index, the index is included in the second list.
    When splitting by item, you can choose whether to keep the split item in the second list.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to split",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        self.split_by = Parameter(
            name="split_by",
            tooltip="How to split the list",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="index",
        )
        self.add_parameter(self.split_by)
        self.split_by.add_trait(Options(choices=["index", "item"]))

        self.split_index = Parameter(
            name="split_index",
            tooltip="Index to split the list at (inclusive)",
            input_types=["int"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"hide": False},
        )
        self.add_parameter(self.split_index)

        self.split_item = Parameter(
            name="split_item",
            tooltip="Item to split the list at",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self.split_item)

        self.keep_split_item = Parameter(
            name="keep_split_item",
            tooltip="Whether to keep the split item in the second list",
            input_types=["bool"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=True,
            ui_options={"hide": True},
        )
        self.add_parameter(self.keep_split_item)

        self.output_a = Parameter(
            name="output_a",
            tooltip="First part of the split list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output_a)

        self.output_b = Parameter(
            name="output_b",
            tooltip="Second part of the split list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output_b)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "split_by":
            if value == "index":
                self.show_parameter_by_name("split_index")
                self.hide_parameter_by_name("split_item")
                self.hide_parameter_by_name("keep_split_item")
            elif value == "item":
                self.hide_parameter_by_name("split_index")
                self.show_parameter_by_name("split_item")
                self.show_parameter_by_name("keep_split_item")
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if not list_values or not isinstance(list_values, list):
            return

        split_by = self.get_parameter_value("split_by")

        if split_by == "index":
            index = self.get_parameter_value("split_index")
            if index is None or not isinstance(index, int):
                return
            if not 0 <= index < len(list_values):
                return

            # Split at index (inclusive)
            self.parameter_output_values["output_a"] = list_values[:index]
            self.parameter_output_values["output_b"] = list_values[index:]

        else:  # split_by == "item"
            item = self.get_parameter_value("split_item")
            if item is None:
                return

            try:
                index = list_values.index(item)
                keep_item = self.get_parameter_value("keep_split_item")

                # Split at item
                self.parameter_output_values["output_a"] = list_values[:index]
                if keep_item:
                    self.parameter_output_values["output_b"] = list_values[index:]
                else:
                    self.parameter_output_values["output_b"] = list_values[index + 1 :]
            except ValueError:
                # Item not found in list
                return
