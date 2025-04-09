from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class ToDictionary(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="from",
                default_value=value,
                input_types=["any"],
                tooltip="The data to convert",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                default_value=value,
                output_type="dict",
                type="dict",
                tooltip="The converted data as dict",
                ui_options={"multiline": True},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        pass

    def to_dict(self, input_value) -> dict:
        result = {}  # Default return value

        try:
            if input_value is None:
                pass  # Keep empty dict
            elif isinstance(input_value, dict):
                result = input_value
            elif isinstance(input_value, str) and input_value.strip():
                result = self._convert_string_to_dict(input_value)
            elif isinstance(input_value, (list, tuple)):
                result = self._convert_sequence_to_dict(input_value)
            elif hasattr(input_value, "__dict__"):
                result = {k: v for k, v in input_value.__dict__.items() if not k.startswith("_")}
            else:
                # Simple values fallback
                result = {"value": input_value}

        except Exception as e:
            logger.debug(f"Exception in to_dict conversion: {e}")
            result = {}  # Reset to empty dict on error

        return result

    def _convert_string_to_dict(self, input_str) -> dict:
        """Convert a string to a dictionary using various parsing strategies."""
        # Try JSON first
        import json

        try:
            parsed = json.loads(input_str)
            if isinstance(parsed, dict):
                result = parsed
            else:
                result = {"value": parsed}
        except json.JSONDecodeError:
            # Process for key-value patterns
            input_str = input_str.strip()
            if ":" in input_str or "=" in input_str:
                result = self._process_key_value_string(input_str)
            else:
                # Default for plain strings
                result = {"value": input_str}

        return result

    def _process_key_value_string(self, input_str) -> dict:
        """Process string with key:value or key=value patterns."""
        result = {}

        # Check for multiple lines
        if "\n" in input_str:
            lines = input_str.split("\n")
            for original_line in lines:
                line_stripped = original_line.strip()
                if not line_stripped:
                    continue

                if ":" in line_stripped:
                    key, value = line_stripped.split(":", 1)
                    result[key.strip()] = value.strip()
                elif "=" in line_stripped:
                    key, value = line_stripped.split("=", 1)
                    result[key.strip()] = value.strip()
        # Single line
        elif ":" in input_str:
            key, value = input_str.split(":", 1)
            result[key.strip()] = value.strip()
        elif "=" in input_str:
            key, value = input_str.split("=", 1)
            result[key.strip()] = value.strip()

        return result

    def _convert_sequence_to_dict(self, sequence) -> dict:
        """Convert a list or tuple to dictionary."""
        result = {}
        length_check = 2
        for i, item in enumerate(sequence):
            if isinstance(item, tuple) and len(item) == length_check:
                key, value = item
                if hasattr(key, "__hash__") and key is not None:
                    result[key] = value
                else:
                    result[f"item{i + 1}"] = item
            else:
                result[f"item{i + 1}"] = item

        return result

    def process(self) -> None:
        # Get the input value
        params = self.parameter_values

        input_value = params.get("from", {})

        self.parameter_output_values["output"] = self.to_dict(input_value)
