from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class DisplayText(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        # Add output parameter for the string
        self.add_parameter(
            ParameterString(
                name="text",
                default_value=value,
                tooltip="The text content to display",
                multiline=True,
                placeholder_text="The text content to display",
            )
        )

    def _update_output(self) -> None:
        """Update the output parameter."""
        text = self.get_parameter_value("text")
        self.parameter_output_values["text"] = text

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "text":
            self._update_output()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
