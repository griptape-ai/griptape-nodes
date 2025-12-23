import json
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class ToList(DataNode):
    """Convert any input value to a list."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="from",
                default_value=value,
                input_types=["any"],
                tooltip="The data to convert to a list",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                default_value=[],
                output_type="list",
                type="list",
                tooltip="The converted data as a list",
                ui_options={"hide_property": True},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def _convert_to_list(self, value: Any) -> list:
        """Convert any value to a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            # If dict has a single key with a list value, return that list directly
            if len(value) == 1:
                single_value = next(iter(value.values()))
                if isinstance(single_value, list):
                    return single_value
            return list(value.values())
        if isinstance(value, str):
            # Try to parse as JSON if it looks like JSON
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    parsed = json.loads(value)
                    # Recursively convert the parsed JSON
                    return self._convert_to_list(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
        # Handle iterables (set, tuple, frozenset) and other types
        return list(value) if isinstance(value, (set, tuple, frozenset)) else [value]

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "from":
            converted = self._convert_to_list(value)
            self.set_parameter_value("output", converted)
            self.publish_update_to_parameter("output", converted)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        input_value = self.get_parameter_value("from")
        converted = self._convert_to_list(input_value)
        self.set_parameter_value("output", converted)
        self.publish_update_to_parameter("output", converted)
