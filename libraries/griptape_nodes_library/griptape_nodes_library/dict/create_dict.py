from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class Dictionary(DataNode):
    """Create a dictionary with arbitrary key-value pairs using list parameters."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of keys
        self.add_parameter(
            Parameter(
                name="keys",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["list[str]"],
                type="list[str]",
                default_value=[],
                tooltip="List of dictionary keys",
            )
        )

        # Add a parameter for a list of values
        self.add_parameter(
            Parameter(
                name="values",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=[
                    "list[str]",
                    "list[int]",
                    "list[float]",
                    "list[bool]",
                    "list",
                ],
                type="list",
                default_value=[],
                tooltip="List of dictionary values",
            )
        )

        # Add dictionary output parameter
        self.add_parameter(
            Parameter(
                name="dict",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value={},
                tooltip="The constructed dictionary",
            )
        )

    def process(self) -> None:
        """Process the node by creating a dictionary from the keys and values lists."""
        # Get the keys and values lists
        keys = self.parameter_values.get("keys", [])
        values = self.parameter_values.get("values", [])

        # Ensure they're actually lists
        if not isinstance(keys, list):
            keys = [keys] if keys is not None else []
        if not isinstance(values, list):
            values = [values] if values is not None else []

        # Build dictionary from keys and values
        result_dict = {}
        for i, key in enumerate(keys):
            # Convert key to string if it's not None
            if key is None:
                new_key = key
            else:
                new_key = str(key)

            # Skip empty or None keys (unless it's the only new_key and has a value)
            if (new_key is None or new_key == "") and (
                len(keys) > 1 or i >= len(values) or values[i] is None or values[i] == ""
            ):
                continue

            # Get matching value or None if index is out of bounds
            value = values[i] if i < len(values) else None

            # Add to dictionary (use empty string as new_key if None)
            result_dict[new_key if new_key is not None else ""] = value

        # Set output values
        self.parameter_output_values["dict"] = result_dict
        self.parameter_values["dict"] = result_dict  # For get_value compatibility
