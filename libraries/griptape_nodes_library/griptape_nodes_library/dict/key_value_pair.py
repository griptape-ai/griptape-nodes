from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class KeyValuePair(DataNode):
    """Create a Key Value Pair."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add dictionary output parameter
        self.add_parameter(
            Parameter(
                name="dictionary",
                output_type="dict",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="Dictionary containing the key-value pair",
            )
        )

    def process(self) -> None:
        """Process the node by creating a key-value pair dictionary."""
        # Set output value
        self.parameter_output_values["dictionary"] = self.parameter_values.get("dictionary", {})
