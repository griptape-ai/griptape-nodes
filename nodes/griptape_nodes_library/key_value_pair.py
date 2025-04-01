from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class KeyValuePairNode(DataNode):
    """Create a Key Value Pair."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add key parameter
        self.add_parameter(
            Parameter(
                name="key",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                default_value="",
                tooltip="The key for the key-value pair",
            )
        )

        # Add value parameter
        self.add_parameter(
            Parameter(
                name="value",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                default_value="",
                tooltip="The value for the key-value pair",
            )
        )

        # Add dictionary output parameter
        self.add_parameter(
            Parameter(
                name="pair",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value={},
                tooltip="The key-value pair as a dictionary",
            )
        )

    def process(self) -> None:
        """Process the node by creating a key-value pair dictionary."""
        key = self.parameter_values.get("key", "")
        value = self.parameter_values.get("value", "")

        # Create dictionary with the key-value pair
        result_dict = {key: value}

        # Set output value
        self.parameter_output_values["pair"] = result_dict
