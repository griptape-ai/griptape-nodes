from itertools import filterfalse
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape.artifacts import ImageArtifact,ImageUrlArtifact


class DisplayList(ControlNode):
    """DisplayList Node that takes a list and creates output parameters for each item in the list.

    This node takes a list as input and creates a new output parameter for each item in the list,
    with the type of the object in the list. This allows for dynamic output parameters based on
    the content of the input list.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            output_type="list",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.items)
        # Spot that will display the list.
        self.items_list = ParameterList(
            name="display_list",
            tooltip="Output list",
            type=ParameterTypeBuiltin.ANY.value,
            allowed_modes={ParameterMode.PROPERTY,ParameterMode.OUTPUT},
            ui_options={"hide":True}
        )
        self.add_parameter(self.items_list)
        # We'll create output parameters dynamically during processing

    def process(self) -> None:
        # Update the display list based on current input
        self._update_display_list()

    def _update_display_list(self) -> None:
        """Update the display list parameters based on current input values."""
        # Clear all dynamically-created parameters at the start
        self._clear_list()

        # Try to get the list of items from the input parameter
        try:
            list_values = self.get_parameter_value("items")
        except Exception:
            # If we can't get the parameter value (e.g., connected node not resolved yet),
            # just clear and return - we'll update again when values are available
            return
        if not list_values or not isinstance(list_values, list):
            items_list_ui_options = self.items_list.ui_options
            items_list_ui_options["hide"] = True
            del items_list_ui_options["display"]
            self.items_list.ui_options = items_list_ui_options
            return
        # Regenerate parameters for each item in the list
        if len(list_values) < 1:
            items_list_ui_options = self.items_list.ui_options
            items_list_ui_options["hide"] = True
            self.items_list.ui_options = items_list_ui_options
            return
        items_list_ui_options = self.items_list.ui_options
        items_list_ui_options["hide"] = False
        self.items_list.ui_options = items_list_ui_options
        item_type = self._determine_item_type(list_values[0])
        self.items_list.type = item_type
        if item_type == "ImageUrlArtifact":
            items_list_ui_options = self.items_list.ui_options
            items_list_ui_options["display"] = "grid"
            self.items_list.ui_options = items_list_ui_options
        for item in list_values:
            # Determine the type of the item
            new_child = self.items_list.add_child_parameter()
            self.set_parameter_value(new_child.name, item)
            self.parameter_output_values[new_child.name] = item

    def _clear_list(self) -> None:
        """Clear all dynamically-created parameters from the node."""
        for child in self.items_list.find_elements_by_type(Parameter):
            # Remove the parameter's output value first
            if child.name in self.parameter_output_values:
                del self.parameter_output_values[child.name]
            try:
                self.remove_parameter_value(child.name)
            except KeyError:
                pass
            # Remove the parameter from the list
        self.items_list.clear_list()

    def _determine_item_type(self, item: Any) -> str:
        """Determine the type of an item for parameter type assignment."""
        if isinstance(item, str):
            return ParameterTypeBuiltin.STR.value
        if isinstance(item, bool):
            return ParameterTypeBuiltin.BOOL.value
        if isinstance(item, int):
            return ParameterTypeBuiltin.INT.value
        if isinstance(item, float):
            return ParameterTypeBuiltin.FLOAT.value
        if isinstance(item, (ImageUrlArtifact, ImageArtifact)):
            return "ImageUrlArtifact"
        return ParameterTypeBuiltin.ANY.value

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update display list when a value is assigned to the items parameter."""
        # Only update if the value was set on our items parameter
        if parameter == self.items:
            self._update_display_list()
        return super().after_value_set(parameter, value)
