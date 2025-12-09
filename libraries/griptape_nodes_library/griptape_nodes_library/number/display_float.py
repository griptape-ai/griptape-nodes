from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayFloat(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: float = 0.0,
    ) -> None:
        super().__init__(name, metadata)

        self.value = value
        self.add_parameter(
            Parameter(
                name="float",
                default_value=self.value,
                type="float",
                tooltip="The number to display",
            )
        )

    def _update_output(self) -> None:
        """Update the output parameter."""
        float_value = self.get_parameter_value("float")
        self.parameter_output_values["float"] = float_value

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if "float" in parameter.name:
            self._update_output()
            self.publish_update_to_parameter("float", value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
