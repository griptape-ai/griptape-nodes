from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


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
    ) -> None:
        super().__init__(name, metadata)

        # Create items_list parameter
        self.items_list = ParameterList(
            name="items",
            tooltip=items_tooltip,
            input_types=input_types,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=default_value,
        )
        self.add_parameter(self.items_list)

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
        self.set_parameter_value(self.output.name, list_values)
        self.parameter_output_values[self.output.name] = list_values
        self.publish_update_to_parameter(self.output.name, list_values)
