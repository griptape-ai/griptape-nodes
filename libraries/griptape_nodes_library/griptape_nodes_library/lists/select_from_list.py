import json
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options


class SelectFromList(ControlNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add list input parameter
        self.list_input = Parameter(
            name="list",
            input_types=["list", "json", "dict"],
            type="list",
            allowed_modes={ParameterMode.INPUT},
            tooltip="List of items to select from, or json/dict to select from keys",
        )
        self.add_parameter(self.list_input)

        # Add selected item parameter
        self.selected_item = ParameterString(
            name="selected_item",
            tooltip="The currently selected item from the list",
            allow_output=True,
            default_value="",
            traits={Options(choices=[])},
        )
        self.add_parameter(self.selected_item)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == self.list_input.name:
            # List input changed, update the selection
            self._update_selected_item()
        elif parameter.name == self.selected_item.name:
            # User manually selected an item, update the output
            self.parameter_output_values[self.selected_item.name] = value
            self.publish_update_to_parameter(self.selected_item.name, value)

        return super().after_value_set(parameter, value)

    def _update_selected_item(self) -> None:
        """Update the selected item based on the current list input."""
        # Get the list
        list_values = self.get_parameter_value(self.list_input.name)

        # Handle failure cases first
        if not list_values:
            self._clear_selection()
            return

        # Handle JSON string input
        if isinstance(list_values, str):
            try:
                parsed = json.loads(list_values)
                if isinstance(parsed, list):
                    list_values = parsed
                elif isinstance(parsed, dict):
                    # Convert dict to list of keys
                    list_values = list(parsed.keys())
                else:
                    self._clear_selection()
                    return
            except (json.JSONDecodeError, TypeError):
                self._clear_selection()
                return

        # Handle dict input - convert to list of keys
        if isinstance(list_values, dict):
            list_values = list(list_values.keys())

        if not isinstance(list_values, list):
            self._clear_selection()
            return

        # Convert all items to strings for consistent comparison
        string_values = [str(item) for item in list_values]

        # Remove duplicates while preserving order
        unique_values = []
        seen = set()
        for item in string_values:
            if item not in seen:
                unique_values.append(item)
                seen.add(item)

        # Update the choices for the dropdown (this handles selection preservation)
        self._update_choices(unique_values)

        # Get the final selected value after choices update
        selected_value = self.get_parameter_value(self.selected_item.name)

        # Update the output
        self.parameter_output_values[self.selected_item.name] = selected_value
        self.publish_update_to_parameter(self.selected_item.name, selected_value)

    def _clear_selection(self) -> None:
        """Clear the current selection and update outputs."""
        self.parameter_output_values[self.selected_item.name] = ""
        self.publish_update_to_parameter(self.selected_item.name, "")

    def _update_choices(self, choices: list[str]) -> None:
        """Update the dropdown choices for the selected_item parameter."""
        # Handle failure case first - empty choices
        if not choices:
            self._update_option_choices("selected_item", [""], "")
            return

        # Get current selection before updating choices
        current_selection = self.get_parameter_value("selected_item")

        # Determine what the default should be
        if current_selection and current_selection in choices:
            # Keep current selection if it's still valid
            default_choice = current_selection
        else:
            # Use first choice if current selection is invalid
            default_choice = choices[0]

        # Use the base class method to update choices
        self._update_option_choices("selected_item", choices, default_choice)

    def process(self) -> None:
        """Process the node - update selection when list input changes."""
        list_values = self.get_parameter_value(self.list_input.name)

        # Only update if we have a valid list
        if list_values and isinstance(list_values, list):
            self._update_selected_item()
