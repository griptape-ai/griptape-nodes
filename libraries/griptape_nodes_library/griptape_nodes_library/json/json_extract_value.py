import json
import re
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class JsonExtractValue(DataNode):
    """Extract a value from JSON using dot notation path."""

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
                tooltip="Input JSON data to extract from",
            )
        )

        # Add parameter for the path to extract
        self.add_parameter(
            Parameter(
                name="path",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Dot notation path to extract (e.g., 'user.name', 'items[0].title')",
                ui_options={"placeholder_text": "Dot notation path to extract (e.g., 'user.name', 'items[0].title')"},
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                type="json",
                tooltip="The extracted value",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _extract_value(self, data: Any, path: str) -> Any:  # noqa: C901, PLR0911
        """Extract a value from nested data using dot notation path."""
        if not path:
            return data

        # Handle array indexing in path (e.g., "items[0].name")
        default = "{}"
        # Split by dots, but preserve array indices
        path_parts = re.split(r"\.(?![^\[]*\])", path)

        current = data

        for part in path_parts:
            if not isinstance(current, (dict, list)):
                return default

            # Check if this part has array indexing
            array_match = re.match(r"^(.+)\[(\d+)\]$", part)
            if array_match:
                # Handle array indexing
                key = array_match.group(1)
                index = int(array_match.group(2))

                if isinstance(current, dict):
                    if key not in current:
                        return default
                    current = current[key]

                if isinstance(current, list):
                    if index < 0 or index >= len(current):
                        return default
                    current = current[index]
                else:
                    return default
            # Handle regular dictionary key
            elif isinstance(current, dict):
                if part not in current:
                    return default
                current = current[part]
            else:
                return default

        return current

    def _perform_extraction(self) -> None:
        """Perform the JSON extraction and set the output value."""
        json_data = self.get_parameter_value("json")
        path = self.get_parameter_value("path")

        # Extract the value
        extracted_value = self._extract_value(json_data, path)

        # Ensure the extracted value is valid JSON
        if extracted_value is None:
            result = "{}"
        else:
            try:
                # Convert the extracted value to valid JSON string
                result = json.dumps(extracted_value, ensure_ascii=False)
            except (TypeError, ValueError):
                # If the value can't be serialized as JSON, return empty object
                result = "{}"

        # Set the output
        self.set_parameter_value("output", result)
        self.publish_update_to_parameter("output", result)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["json", "path"]:
            self._perform_extraction()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by extracting the value at the specified path."""
        self._perform_extraction()
