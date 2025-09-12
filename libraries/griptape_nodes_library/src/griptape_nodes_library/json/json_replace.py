import copy
import re
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


class JsonReplace(ControlNode):
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

    def _parse_array_index(self, part: str) -> tuple[str | None, int | None]:
        """Parse array indexing from path part (e.g., 'items[0]' -> ('items', 0))."""
        match = re.match(r"^(.+)\[(\d+)\]$", part)
        return (match.group(1), int(match.group(2))) if match else (None, None)

    def _ensure_dict_has_list(self, current: Any, key: str) -> Any:
        """Ensure a dictionary has a list at the specified key."""
        if isinstance(current, dict):
            if key not in current:
                current[key] = []
            return current[key]
        return current

    def _ensure_list_has_index(self, current: Any, index: int) -> Any:
        """Ensure a list has enough elements to access the specified index."""
        if isinstance(current, list):
            while len(current) <= index:
                current.append({} if index < len(current) else None)
            return current[index]
        return None

    def _handle_array_part(self, current: Any, key: str, index: int) -> Any:
        """Handle array indexing in path traversal."""
        # Ensure the current container has the required list
        current = self._ensure_dict_has_list(current, key)

        # Ensure the list has enough elements for the index
        return self._ensure_list_has_index(current, index)

    def _split_path_into_parts(self, path: str) -> list[str]:
        """Split a dot notation path into parts, respecting array brackets."""
        return re.split(r"\.(?![^\[]*\])", path)

    def _is_valid_container(self, obj: Any) -> bool:
        """Check if an object is a valid container (dict or list) for path traversal."""
        return isinstance(obj, (dict, list))

    def _handle_path_part(self, current: Any, part: str) -> Any:
        """Handle a single path part (either array index or dictionary key)."""
        key, index = self._parse_array_index(part)

        if key and index is not None:
            # Handle array indexing
            current = self._handle_array_part(current, key, index)
            if current is None:
                return None
        elif isinstance(current, dict):
            # Handle dictionary key
            if part not in current:
                current[part] = {}
            current = current[part]
        else:
            # Invalid container type
            return None

        return current

    def _navigate_to_parent_container(self, data: Any, path_parts: list[str]) -> tuple[Any, str]:
        """Navigate through the path to reach the parent container of the target location."""
        current = data

        # Navigate through all parts except the last one
        for part in path_parts[:-1]:
            if not self._is_valid_container(current):
                return None, ""

            current = self._handle_path_part(current, part)
            if current is None:
                return None, ""

        return current, path_parts[-1]

    def _set_value_in_container(self, container: Any, final_part: str, new_value: Any) -> None:
        """Set the value in the final container at the specified part."""
        key, index = self._parse_array_index(final_part)

        if key and index is not None:
            # Handle array indexing for final part
            container = self._handle_array_part(container, key, index)
            if isinstance(container, list):
                container[index] = new_value
        elif isinstance(container, dict):
            # Handle dictionary key for final part
            container[final_part] = new_value

    def _set_value_at_path(self, data: Any, path: str, new_value: Any) -> Any:
        """Set a value at a specific path in nested data using dot notation."""
        # Handle empty path case
        if not path:
            return new_value

        # Create a deep copy to avoid modifying the original data
        result = copy.deepcopy(data)

        # Split the path into manageable parts
        path_parts = self._split_path_into_parts(path)

        # Navigate to the parent container
        parent_container, final_part = self._navigate_to_parent_container(result, path_parts)

        # If navigation failed, return the original data
        if parent_container is None:
            return result

        # Set the value in the final container
        self._set_value_in_container(parent_container, final_part, new_value)

        return result

    def _get_input_parameters(self) -> tuple[Any, str, Any]:
        """Get the input parameters for the replacement operation."""
        json_data = self.get_parameter_value("json")
        path = self.get_parameter_value("path")
        replacement_value = self.get_parameter_value("replacement_value")
        return json_data, path, replacement_value

    def _update_output_parameter(self, result: Any) -> None:
        """Update the output parameter with the result."""
        self.set_parameter_value("output", result)
        self.publish_update_to_parameter("output", result)

    def _perform_replacement(self) -> None:
        """Perform the JSON replacement and set the output value."""
        # Get input parameters
        json_data, path, replacement_value = self._get_input_parameters()

        # Perform the replacement operation
        result = self._set_value_at_path(json_data, path, replacement_value)

        # Update the output parameter
        self._update_output_parameter(result)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["json", "path", "replacement_value"]:
            self._perform_replacement()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by replacing the value at the specified path."""
        self._perform_replacement()
