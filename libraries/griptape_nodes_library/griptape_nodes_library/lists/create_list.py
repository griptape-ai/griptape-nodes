from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import ControlNode


class CreateList(ControlNode):
    """CreateList Node that that creates a list with items provided."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = ParameterList(
            name="items",
            tooltip="List of items to add to",
            input_types=[ParameterTypeBuiltin.ANY.value],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.items_list)
        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        # If items parameter was set, update output immediately
        if param_name == self.items_list.name:
            self._update_output()

    def process(self) -> None:
        self._update_output()

    def _update_output(self) -> None:
        """Gets items, sets output value, and publishes update."""
        list_values = self.get_parameter_value(self.items_list.name)
        self.set_parameter_value(self.output.name, list_values)
        self.parameter_output_values[self.output.name] = list_values

        self.publish_update_to_parameter(self.output.name, list_values)
