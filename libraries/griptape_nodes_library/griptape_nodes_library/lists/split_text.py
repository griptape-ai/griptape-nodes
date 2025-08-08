from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options


class SplitText(ControlNode):
    """SplitText Node that takes a text string and splits it into a list based on a specified delimiter."""

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
        self.text_input = Parameter(
            name="text",
            tooltip="Text string to split",
            type="str",
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT},
            ui_options={"multiline": True},
        )
        self.add_parameter(self.text_input)

        # Add delimiter type parameter
        self.delimiter_type = Parameter(
            name="delimiter_type",
            tooltip="Type of delimiter to use for splitting",
            type="str",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="newlines",
        )
        self.add_parameter(self.delimiter_type)
        self.delimiter_type.add_trait(Options(choices=list(self.DELIMITER_MAP.keys())))

        # Add include delimiter option
        self.include_delimiter = Parameter(
            name="include_delimiter",
            tooltip="Whether to include the delimiter in the split results",
            type="bool",
            input_types=["bool"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value=False,
        )
        self.add_parameter(self.include_delimiter)

        # Add trim whitespace option
        self.trim_whitespace = Parameter(
            name="trim_whitespace",
            tooltip="Whether to trim leading whitespace after the delimiter",
            type="bool",
            input_types=["bool"],
            allowed_modes={ParameterMode.PROPERTY},
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

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in [
            self.text_input.name,
            self.delimiter_type.name,
            self.include_delimiter.name,
            self.trim_whitespace.name,
        ]:
            self._process_text()
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
        """Process the text input and split it according to the selected delimiter."""
        # Get the text and delimiter type from input parameters
        text = self.get_parameter_value(self.text_input.name)
        delimiter_type = self.get_parameter_value(self.delimiter_type.name)
        include_delimiter = self.get_parameter_value(self.include_delimiter.name)
        trim_whitespace = self.get_parameter_value(self.trim_whitespace.name)

        # Determine the actual delimiter based on type
        actual_delimiter = self.DELIMITER_MAP.get(delimiter_type, "\n")  # default to newlines

        # Split the text by the delimiter
        try:
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

            self.parameter_output_values[self.output.name] = split_result
            self.publish_update_to_parameter(self.output.name, split_result)
        except (TypeError, ValueError) as e:
            # Handle type or value errors
            msg = f"{self.name}: Error splitting text: {e}"
            logger.error(msg)
            self.parameter_output_values[self.output.name] = []
            self.publish_update_to_parameter(self.output.name, [])

    def process(self) -> None:
        self._process_text()
