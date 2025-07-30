from typing import Any

from json_repair import repair_json

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayJson(DataNode):
    """Create a JSON Display node."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of keys
        self.add_parameter(
            Parameter(
                name="json",
                input_types=["json", "str", "dict"],
                type="json",
                default_value="{}",
                tooltip="Json Data",
            )
        )

    def process(self) -> None:
        json_data = self.get_parameter_value("json")

        # Handle different input types
        if isinstance(json_data, dict):
            # If it's already a dict, use it as is
            result = json_data
        elif isinstance(json_data, str):
            # If it's a string, try to repair and parse it
            try:
                result = repair_json(json_data)
            except Exception as e:
                msg = f"DisplayJson: Failed to repair JSON string: {e}. Input: {json_data[:200]!r}"
                raise ValueError(msg) from e
        else:
            # For other types, convert to string and try to repair
            try:
                result = repair_json(str(json_data))
            except Exception as e:
                msg = f"DisplayJson: Failed to convert input to JSON: {e}. Input type: {type(json_data)}, value: {json_data!r}"
                raise ValueError(msg) from e

        self.parameter_output_values["json"] = result
