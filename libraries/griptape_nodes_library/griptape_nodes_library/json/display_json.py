import json
import re
from enum import StrEnum
from typing import Any

import yaml
from json_repair import repair_json

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode

KEY_VALUE_PARTS = 2
MIN_YAML_LINES = 2


class FormatType(StrEnum):
    """Supported format types for data parsing."""

    JSON = "json"
    YAML = "yaml"
    UNKNOWN = "unknown"


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

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON from markdown code blocks."""
        # Pattern to match ```json ... ``` or ``` ... ``` blocks
        json_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
        match = re.search(json_block_pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()
        return text

    def _extract_yaml_from_markdown(self, text: str) -> str:
        """Extract YAML from markdown code blocks."""
        # Pattern to match ```yaml ... ``` or ```yml ... ``` blocks
        yaml_block_pattern = r"```(?:yaml|yml)?\s*\n(.*?)\n```"
        match = re.search(yaml_block_pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()
        return text

    def _detect_format(self, text: str) -> FormatType:
        """Detect if the text is JSON, YAML, or plain text."""
        stripped = text.strip()

        # Check for JSON-like structure
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            return FormatType.JSON

        # Check for YAML-like structure - more conservative approach
        lines = stripped.split("\n")
        yaml_like_lines = 0
        total_lines = 0

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):  # Skip empty lines and comments
                continue
            total_lines += 1

            # Look for key: value patterns (but not URLs or other colons)
            if ":" in stripped_line and not stripped_line.startswith(("http", "#")):
                # Check if it's a proper key: value pattern
                parts = stripped_line.split(":", 1)
                if len(parts) == KEY_VALUE_PARTS and parts[0].strip() and not parts[0].strip().startswith("#"):
                    yaml_like_lines += 1
            # Look for list items
            elif stripped_line.startswith(("- ", "  - ")) or stripped_line in ("---", "..."):
                yaml_like_lines += 1

        # Only classify as YAML if we have a reasonable number of YAML-like lines
        # Be more lenient - if most lines look like YAML, classify as YAML
        if total_lines > 0 and (yaml_like_lines >= MIN_YAML_LINES or yaml_like_lines >= total_lines * 0.7):
            return FormatType.YAML

        return FormatType.UNKNOWN

    def _validate_and_parse_json(self, json_str: str) -> Any:
        """Validate and parse JSON string, with repair if needed."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to repair the JSON
            try:
                return repair_json(json_str)
            except Exception as e:
                msg = f"DisplayJson: Failed to repair JSON string: {e}. Input: {json_str[:200]!r}"
                raise ValueError(msg) from e

    def _validate_and_parse_yaml(self, yaml_str: str) -> Any:
        """Validate and parse YAML string."""
        try:
            return yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            msg = f"DisplayJson: Failed to parse YAML string: {e}. Input: {yaml_str[:200]!r}"
            raise ValueError(msg) from e

    def _process_json_data(self) -> None:
        """Process the JSON data and update the output."""
        json_data = self.get_parameter_value("json")

        # Handle different input types
        if isinstance(json_data, dict):
            # If it's already a dict, use it as is
            result = json_data
        elif isinstance(json_data, str):
            # Check if the string contains markdown code blocks
            extracted_content = self._extract_json_from_markdown(json_data)

            # If no JSON markdown found, try YAML markdown
            if extracted_content == json_data:
                extracted_content = self._extract_yaml_from_markdown(json_data)

            # Detect format and parse accordingly
            format_type = self._detect_format(extracted_content)

            if format_type == FormatType.JSON:
                result = self._validate_and_parse_json(extracted_content)
            elif format_type == FormatType.YAML:
                result = self._validate_and_parse_yaml(extracted_content)
            else:
                # Try JSON first, then YAML as fallback
                try:
                    result = self._validate_and_parse_json(extracted_content)
                except ValueError:
                    try:
                        result = self._validate_and_parse_yaml(extracted_content)
                    except ValueError as e:
                        msg = f"DisplayJson: Failed to parse input as JSON or YAML: {e}. Input: {extracted_content[:200]!r}"
                        raise ValueError(msg) from e
        else:
            # For other types, convert to string and try to repair
            try:
                result = repair_json(str(json_data))
            except Exception as e:
                msg = f"DisplayJson: Failed to convert input to JSON: {e}. Input type: {type(json_data)}, value: {json_data!r}"
                raise ValueError(msg) from e

        self.parameter_output_values["json"] = result
        self.publish_update_to_parameter("json", result)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Process JSON data when the input parameter changes."""
        if parameter.name == "json":
            self._process_json_data()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by parsing and displaying JSON data."""
        self._process_json_data()
