from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class JsonReplace(DataNode):
    """Replace a value in JSON using dot notation path."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add parameter for input JSON
        self.add_parameter(
            Parameter(
                name="json",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["json", "str", "dict"],
                type="json",
                default_value="{}",
                tooltip="Input JSON data to modify",
            )
        )

        # Add parameter for the path to replace
        self.add_parameter(
            Parameter(
                name="path",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Dot notation path to replace (e.g., 'user.name', 'items[0].title')",
                ui_options={"placeholder_text": "Dot notation path to replace (e.g., 'user.name', 'items[0].title')"},
            )
        )

        # Add parameter for the replacement value
        self.add_parameter(
            Parameter(
                name="replacement_value",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["json", "str", "dict"],
                type="json",
                default_value="",
                tooltip="The new value to put at the specified path",
            )
        )

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="json",
                tooltip="The modified JSON with the replacement value",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"placeholder_text": "The modified JSON with the replacement value"},
            )
        )

    def _set_value_at_path(self, data: Any, path: str, new_value: Any) -> Any:
        """Set a value at a specific path in nested data using dot notation."""
        if not path:
            return new_value

        # Create a deep copy to avoid modifying the original
        import copy

        result = copy.deepcopy(data)

        # Handle array indexing in path (e.g., "items[0].name")
        import re

        # Split by dots, but preserve array indices
        path_parts = re.split(r"\.(?![^\[]*\])", path)

        current = result

        # Navigate to the parent of the target location
        for i, part in enumerate(path_parts[:-1]):
            if not isinstance(current, (dict, list)):
                # If we can't navigate further, create the path
                if i == 0:
                    current = {}
                else:
                    return result

            # Check if this part has array indexing
            array_match = re.match(r"^(.+)\[(\d+)\]$", part)
            if array_match:
                # Handle array indexing
                key = array_match.group(1)
                index = int(array_match.group(2))

                if isinstance(current, dict):
                    if key not in current:
                        current[key] = []
                    current = current[key]

                if isinstance(current, list):
                    # Extend list if index is out of bounds
                    while len(current) <= index:
                        current.append({})
                    current = current[index]
                else:
                    return result
            # Handle regular dictionary key
            elif isinstance(current, dict):
                if part not in current:
                    current[part] = {}
                current = current[part]
            else:
                return result

        # Set the value at the final path part
        final_part = path_parts[-1]
        array_match = re.match(r"^(.+)\[(\d+)\]$", final_part)

        if array_match:
            # Handle array indexing for the final part
            key = array_match.group(1)
            index = int(array_match.group(2))

            if isinstance(current, dict):
                if key not in current:
                    current[key] = []
                current = current[key]

            if isinstance(current, list):
                # Extend list if index is out of bounds
                while len(current) <= index:
                    current.append(None)
                current[index] = new_value
        # Handle regular dictionary key for the final part
        elif isinstance(current, dict):
            current[final_part] = new_value

        return result

    def _perform_replacement(self) -> None:
        """Perform the JSON replacement and set the output value."""
        json_data = self.get_parameter_value("json")
        path = self.get_parameter_value("path")
        replacement_value = self.get_parameter_value("replacement_value")

        # Replace the value at the specified path
        result = self._set_value_at_path(json_data, path, replacement_value)

        # Set the output
        self.set_parameter_value("output", result)
        self.publish_update_to_parameter("output", result)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["json", "path", "replacement_value"]:
            self._perform_replacement()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by replacing the value at the specified path."""
        self._perform_replacement()
