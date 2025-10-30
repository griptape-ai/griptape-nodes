import json
from typing import Any

import jmespath  # pyright: ignore[reportMissingImports, reportMissingModuleSource]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class JsonExtractValue(DataNode):
    """Extract values from JSON using JMESPath expressions."""

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

        # Add parameter for the JMESPath expression
        self.add_parameter(
            ParameterString(
                name="path",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                tooltip="JMESPath expression to extract data (e.g., 'user.name', 'items[0].title', '[*].assignee' for all assignees)",
                placeholder_text="ex: user.name, items[0].title, [*].assignee",
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                type="json",
                tooltip="The extracted value(s)",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def _perform_extraction(self) -> None:
        """Perform the JSON extraction using JMESPath."""
        json_data = self.get_parameter_value("json")
        path = self.get_parameter_value("path")

        # Parse JSON string if needed - failure cases first
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except json.JSONDecodeError as e:
                msg = f"{self.name}: Invalid JSON string provided. Failed to parse JSON: {e}. Input was: {json_data[:200]!r}"
                raise ValueError(msg) from e
            except TypeError as e:
                msg = f"{self.name}: Unable to parse JSON data due to type error: {e}. Input type: {type(json_data)}, value: {json_data[:200]!r}"
                raise ValueError(msg) from e

        # Extract value using JMESPath - failure cases first
        if not path:
            result = json_data
        else:
            try:
                result = jmespath.search(path, json_data)
            except (ValueError, TypeError) as e:
                msg = f"{self.name}: Invalid JMESPath expression '{path}': {e}"
                raise ValueError(msg) from e

        # Handle None result - return empty dict like other JSON nodes
        if result is None:
            result = {}

        # Success path at the end - return raw Python value (no JSON serialization needed)
        # JMESPath already returns the correct Python types (str, dict, list, etc.)
        GriptapeNodes.handle_request(
            SetParameterValueRequest(parameter_name="output", value=result, node_name=self.name)
        )
        self.publish_update_to_parameter("output", result)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["json", "path"]:
            self._perform_extraction()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by extracting the value at the specified path."""
        self._perform_extraction()
