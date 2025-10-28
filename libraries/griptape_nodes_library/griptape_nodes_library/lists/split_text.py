import ast
import json
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options


class SplitText(ControlNode):
    """SplitText Node that can either split text by delimiter or parse it as a list.

    This node provides two modes of operation:
    1. Split mode: Splits text by a specified delimiter (original behavior)
    2. Parse mode: Intelligently parses text as JSON/Python lists with fallback to delimiter splitting

    Key Features:
    - Multiple delimiter options (comma, semicolon, pipe, etc.)
    - Intelligent list parsing (JSON, Python literals, comma-separated)
    - Whitespace trimming and delimiter inclusion options
    - Robust error handling and fallback mechanisms
    """

    # Central definition of delimiter choices and their mappings
    DELIMITER_MAP: ClassVar[dict[str, str]] = {
        "newlines": "\n",
        "double_newline": "\n\n",
        "space": " ",
        "comma": ",",
        "semicolon": ";",
        "colon": ":",
        "tab": "\t",
        "pipe": "|",
        "dash": "-",
        "underscore": "_",
        "period": ".",
        "slash": "/",
        "backslash": "\\",
        "at": "@",
        "hash": "#",
        "ampersand": "&",
        "equals": "=",
    }

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input text parameter
        self.text_input = ParameterString(
            name="text",
            tooltip="Text string to split",
            allow_output=False,
            multiline=True,
        )
        self.add_parameter(self.text_input)

        # Add split mode parameter (moved up to control visibility of other parameters)
        self.split_mode = ParameterString(
            name="split_mode",
            tooltip="How to process the text: split by delimiter or parse as list",
            allow_output=False,
            allow_input=False,
            default_value="split",
        )
        self.add_parameter(self.split_mode)
        self.split_mode.add_trait(Options(choices=["split", "parse_list"]))

        # Add delimiter type parameter
        self.delimiter_type = ParameterString(
            name="delimiter_type",
            tooltip="Type of delimiter to use for splitting",
            allow_output=False,
            allow_input=False,
            default_value="newlines",
        )
        self.add_parameter(self.delimiter_type)
        self.delimiter_type.add_trait(Options(choices=list(self.DELIMITER_MAP.keys())))

        # Add include delimiter option
        self.include_delimiter = ParameterBool(
            name="include_delimiter",
            tooltip="Whether to include the delimiter in the split results",
            allow_output=False,
            default_value=False,
        )
        self.add_parameter(self.include_delimiter)

        # Add trim whitespace option
        self.trim_whitespace = ParameterBool(
            name="trim_whitespace",
            tooltip="Whether to trim leading whitespace after the delimiter",
            on_label="trim",
            off_label="keep",
            allow_output=False,
            default_value=False,
        )
        self.add_parameter(self.trim_whitespace)

        # Add output parameter
        self.output = Parameter(
            name="output",
            tooltip="List of text items",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

        # Set initial parameter visibility
        self._update_parameter_visibility()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in [
            self.text_input.name,
            self.delimiter_type.name,
            self.include_delimiter.name,
            self.trim_whitespace.name,
            self.split_mode.name,
        ]:
            self._process_text()

        # Control parameter visibility based on split_mode
        if parameter.name == self.split_mode.name:
            if value == "parse_list":
                self.hide_parameter_by_name("delimiter_type")
                self.hide_parameter_by_name("include_delimiter")
            else:
                self.show_parameter_by_name("delimiter_type")
                self.show_parameter_by_name("include_delimiter")

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception]:
        exceptions = []
        text = self.get_parameter_value(self.text_input.name)
        if text is None:
            exceptions.append(Exception(f"{self.name}: Text is required to split"))
        elif not isinstance(text, str):
            exceptions.append(Exception(f"{self.name}: Text must be a string"))
        return exceptions

    def _process_text(self) -> None:
        """Process the text input according to the selected mode (split or parse)."""
        # Get all input parameters
        text = self.get_parameter_value(self.text_input.name)
        split_mode = self.get_parameter_value(self.split_mode.name)
        delimiter_type = self.get_parameter_value(self.delimiter_type.name)
        include_delimiter = self.get_parameter_value(self.include_delimiter.name)
        trim_whitespace = self.get_parameter_value(self.trim_whitespace.name)

        # Ensure text is a string
        if not isinstance(text, str):
            text = ""

        try:
            if split_mode == "parse_list":
                # Parse mode: intelligently parse as list
                split_result = self._parse_as_list(text, delimiter_type, trim_whitespace=trim_whitespace)
            else:
                # Split mode: original delimiter-based splitting
                split_result = self._split_by_delimiter(
                    text, delimiter_type, include_delimiter=include_delimiter, trim_whitespace=trim_whitespace
                )

            self.parameter_output_values[self.output.name] = split_result
            self.publish_update_to_parameter(self.output.name, split_result)
        except (TypeError, ValueError) as e:
            # Handle type or value errors
            msg = f"{self.name}: Error processing text: {e}"
            logger.error(msg)
            self.parameter_output_values[self.output.name] = []
            self.publish_update_to_parameter(self.output.name, [])

    def _split_by_delimiter(
        self, text: str, delimiter_type: str, *, include_delimiter: bool, trim_whitespace: bool
    ) -> list[str]:
        """Split text by delimiter (original behavior)."""
        # Determine the actual delimiter based on type
        actual_delimiter = self.DELIMITER_MAP.get(delimiter_type, "\n")  # default to newlines

        # Split the text by the delimiter
        if include_delimiter:
            # Split and append delimiters to preceding elements
            split_result = text.split(actual_delimiter)
            # Append delimiter to each element except the last one
            for i in range(len(split_result) - 1):
                split_result[i] += actual_delimiter
        else:
            # Standard split without including delimiter
            split_result = text.split(actual_delimiter)

        # Apply whitespace trimming if requested
        if trim_whitespace:
            split_result = [item.lstrip() for item in split_result]

        return split_result

    def _parse_as_list(self, text: str, delimiter_type: str, *, trim_whitespace: bool) -> list[str]:
        """Intelligently parse text as a list with fallback to delimiter splitting."""
        # Try JSON parsing first (for double-quoted lists like '["one", "two"]')
        try:
            parsed_list = json.loads(text)
            if isinstance(parsed_list, list):
                return [str(item) for item in parsed_list]
            return [str(parsed_list)]
        except (json.JSONDecodeError, ValueError):
            pass

        # Try Python literal evaluation (for single-quoted lists like "['one', 'two']")
        try:
            parsed_list = ast.literal_eval(text)
            if isinstance(parsed_list, list):
                return [str(item) for item in parsed_list]
            return [str(parsed_list)]
        except (ValueError, SyntaxError):
            pass

        # Try comma-separated parsing (for cases like "one, two, three")
        if "," in text:
            result = [item.strip() for item in text.split(",")]
            if trim_whitespace:
                result = [item.lstrip() for item in result]
            return result

        # Fallback to delimiter splitting
        actual_delimiter = self.DELIMITER_MAP.get(delimiter_type, "\n")
        result = text.split(actual_delimiter)
        if trim_whitespace:
            result = [item.lstrip() for item in result]
        return result

    def _update_parameter_visibility(self) -> None:
        """Update parameter visibility based on split_mode."""
        split_mode = self.get_parameter_value(self.split_mode.name)

        if split_mode == "parse_list":
            # Hide delimiter-specific parameters when in parse_list mode
            self.hide_parameter_by_name("delimiter_type")
            self.hide_parameter_by_name("include_delimiter")
            # Keep trim_whitespace visible as it's still useful for parsing
        else:
            # Show all parameters when in split mode
            self.show_parameter_by_name("delimiter_type")
            self.show_parameter_by_name("include_delimiter")

    def process(self) -> None:
        self._process_text()
