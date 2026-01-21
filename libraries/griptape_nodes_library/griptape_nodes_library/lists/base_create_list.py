from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool


class BaseCreateListNode(ControlNode):
    """Base class for all create list nodes."""

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        metadata: dict[Any, Any] | None,
        *,
        input_types: list[str],
        output_type: str,
        default_value: Any,
        items_tooltip: str,
        ui_options: dict[str, Any] | None = None,
    ) -> None:
        if ui_options is None:
            ui_options = {"hide_property": True}
        super().__init__(name, metadata)

        # Create items_list parameter
        self.items_list = ParameterList(
            name="items",
            tooltip=items_tooltip,
            input_types=input_types,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=default_value,
            ui_options=ui_options,
        )
        self.add_parameter(self.items_list)

        with ParameterGroup(name="list_options", ui_options={"collapsed": True}) as list_options_group:
            self.flatten_list = ParameterBool(
                name="flatten_list",
                tooltip="Flatten the list into a single list",
                default_value=False,
            )

            self.remove_duplicates = ParameterBool(
                name="remove_duplicates",
                tooltip="Remove duplicates from the list",
                default_value=False,
            )

            self.remove_blank = ParameterBool(
                name="remove_blank",
                tooltip="Remove blank items from the list",
                default_value=False,
            )

        self.add_node_element(list_options_group)

        # Create output parameter
        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type=output_type,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # If items parameter or any child of items_list was set, update output immediately
        if parameter.name.startswith(f"{self.items_list.name}_"):
            self._update_output()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        self._update_output()

    def _update_output(self) -> None:
        """Gets items, sets output value, and publishes update."""
        list_values = self.get_parameter_value(self.items_list.name)
        flatten_list = self.get_parameter_value(self.flatten_list.name)
        remove_duplicates = self.get_parameter_value(self.remove_duplicates.name)
        remove_blank = self.get_parameter_value(self.remove_blank.name)

        if flatten_list:
            # Check if list is already flat (no nested lists)
            has_nested_lists = any(isinstance(item, list) for item in list_values)
            if has_nested_lists:
                # Flatten only if there are nested lists
                flattened = []
                for item in list_values:
                    if isinstance(item, list):
                        flattened.extend(item)
                    else:
                        flattened.append(item)
                list_values = flattened

        if remove_duplicates:
            list_values = list(set(list_values))

        if remove_blank:
            list_values = [item for item in list_values if item is not None and item.strip() != ""]

        self.parameter_output_values[self.output.name] = list_values

        # Publish update to propagate the output value
        self.publish_update_to_parameter(self.output.name, list_values)
