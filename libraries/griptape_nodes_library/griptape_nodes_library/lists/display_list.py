from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger


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
            tooltip="Output list. Your values will propagate in these inputs here.",
            type=ParameterTypeBuiltin.ANY.value,
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide_property": False},
        )
        self.add_parameter(self.items_list)
        # Track whether we're already updating to prevent duplicate calls
        self._updating_display_list = False
        # We'll create output parameters dynamically during processing

    def process(self) -> None:
        # During process, we want to clean up parameters if the list is too long
        self._update_display_list(delete_excess_parameters=True)

    def _update_display_list(self, *, delete_excess_parameters: bool = False) -> None:
        """Update the display list parameters based on current input values.

        Args:
            delete_excess_parameters: If True, delete parameters when list is shorter than parameter count.
                                    If False, keep existing parameters even when list is shorter.
        """
        # Prevent duplicate calls
        if self._updating_display_list:
            logger.debug(
                "DisplayList._update_display_list(): Already updating for node %s, skipping duplicate call",
                self.name,
            )
            return

        self._updating_display_list = True

        # Try to get the list of items from the input parameter
        try:
            list_values = self.get_parameter_value("items")
        except Exception:
            self._clear_list()
            # If we can't get the parameter value (e.g., connected node not resolved yet),
            # just clear and return - we'll update again when values are available
            self._updating_display_list = False
            return

        # Prepare ui_options update in one go to avoid multiple change events
        new_ui_options = self.items_list.ui_options.copy()

        # If it's None or not a list...
        if not isinstance(list_values, list):
            if "display" in new_ui_options:
                # Remove display from the ui_options so non-image parameters will properly display.
                del new_ui_options["display"]
            self.items_list.ui_options = new_ui_options
            self._updating_display_list = False
            return

        # Regenerate parameters for each item in the list
        if len(list_values) == 0:
            # If we're empty, be empty.
            self._clear_list()
            self.items_list.ui_options = new_ui_options
            self._updating_display_list = False
            return

        new_ui_options["hide"] = False
        item_type = self._determine_item_type(list_values[0])
        self._configure_list_type_and_ui(item_type, new_ui_options)
        # Only delete excess parameters if explicitly requested (e.g., during process())
        if delete_excess_parameters:
            self.delete_excess_parameters(list_values)
        for i, item in enumerate(list_values):
            if i < len(self.items_list):
                current_parameter = self.items_list[i]
                self.set_parameter_value(current_parameter.name, item)
                # Using to ensure updates are being propagated
                self.publish_update_to_parameter(current_parameter.name, item)
                self.parameter_output_values[current_parameter.name] = item
                continue
            new_child = self.items_list.add_child_parameter()
            # Set the parameter value
            self.set_parameter_value(new_child.name, item)
            # Ensure the new child parameter is tracked for flush events
        self._updating_display_list = False

    def delete_excess_parameters(self, list_values: list) -> None:
        """Delete parameters when list is shorter than parameter count."""
        length_of_items_list = len(self.items_list)
        while length_of_items_list > len(list_values):
            # Remove the parameter value - this will also handle parameter_output_values
            if self.items_list[length_of_items_list - 1].name in self.parameter_values:
                self.remove_parameter_value(self.items_list[length_of_items_list - 1].name)
            if self.items_list[length_of_items_list - 1].name in self.parameter_output_values:
                del self.parameter_output_values[self.items_list[length_of_items_list - 1].name]
            # Remove the parameter from the list
            self.items_list.remove_child(self.items_list[length_of_items_list - 1])
            length_of_items_list = len(self.items_list)

    def _clear_list(self) -> None:
        """Clear all dynamically-created parameters from the node."""
        for child in self.items_list.find_elements_by_type(Parameter):
            # Remove the parameter value - this will also handle parameter_output_values
            # We are suppressing the error, which will be raised if the parameter is not in parameter_values.
            # This is ok, because we are just trying to remove the parameter value IF it exists.
            if child.name in self.parameter_values:
                self.remove_parameter_value(child.name)
            if child.name in self.parameter_output_values:
                del self.parameter_output_values[child.name]
            # Remove the parameter from the list
        self.items_list.clear_list()

    def _configure_list_type_and_ui(self, item_type: str, ui_options: dict[str, Any]) -> None:
        """Configure the items_list parameter type and UI options based on item type.

        Args:
            item_type: The type string for list items
            ui_options: Dictionary of UI options to configure
        """
        # Configure UI options for dict display
        if item_type == "dict":
            ui_options["multiline"] = True
            ui_options["placeholder_text"] = "The dictionary content will be displayed here."

        # We have to change all three because parameters are created with all three initialized.
        self.items_list.type = item_type
        if item_type == ParameterTypeBuiltin.ANY.value:
            self.items_list.output_type = ParameterTypeBuiltin.ALL.value
        else:
            self.items_list.output_type = item_type
        self.items_list.input_types = [item_type]
        self.items_list.ui_options = ui_options

    def _determine_item_type(self, item: Any) -> str:
        """Determine the type of an item for parameter type assignment."""
        result = ParameterTypeBuiltin.ANY.value
        if isinstance(item, bool):
            result = ParameterTypeBuiltin.BOOL.value
        elif isinstance(item, str):
            result = ParameterTypeBuiltin.STR.value
        elif isinstance(item, int):
            result = ParameterTypeBuiltin.INT.value
        elif isinstance(item, float):
            result = ParameterTypeBuiltin.FLOAT.value
        elif isinstance(item, dict):
            result = "dict"
        elif isinstance(item, (ImageUrlArtifact, ImageArtifact)):
            result = "ImageUrlArtifact"
        return result

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update display list when a value is assigned to the items parameter."""
        # Only update if the value was set on our items parameter
        if parameter == self.items:
            logger.debug(
                f"DisplayList.after_value_set(): Items parameter updated for node {self.name}, triggering display list update"
            )
            self._update_display_list()
        return super().after_value_set(parameter, value)

    def after_incoming_connection_removed(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        self._update_display_list()
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)
