import re
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options


class SplitText(ControlNode):
    """SplitText Node that takes a text string and splits it into a list based on a specified delimiter."""

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
        self.delimiter_type.add_trait(
            Options(choices=["newlines", "space", "comma", "semicolon", "tab", "pipe", "dash", "underscore"])
        )

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

        # Add output parameter
        self.output = Parameter(
            name="output",
            tooltip="List of text items",
            type="list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name in ["text", "delimiter_type", "include_delimiter"]:
            self._process_text()
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception]:
        exceptions = []
        text = self.get_parameter_value("text")
        if text is None:
            exceptions.append(Exception(f"{self.name}: Text is required to split"))
        elif not isinstance(text, str):
            exceptions.append(Exception(f"{self.name}: Text must be a string"))
        return exceptions

    def _process_text(self) -> None:
        """Process the text input and split it according to the selected delimiter."""
        # Get the text and delimiter type from input parameters
        text = self.get_parameter_value("text")
        delimiter_type = self.get_parameter_value("delimiter_type")
        include_delimiter = self.get_parameter_value("include_delimiter")

        # Determine the actual delimiter based on type
        delimiter_map = {
            "newlines": "\n",
            "space": " ",
            "comma": ",",
            "semicolon": ";",
            "tab": "\t",
            "pipe": "|",
            "dash": "-",
            "underscore": "_",
        }
        actual_delimiter = delimiter_map.get(delimiter_type, "\n")  # default to newlines

        # Split the text by the delimiter
        try:
            if include_delimiter:
                # Split and keep the delimiter using regex (delimiters are predefined and safe)
                # All delimiters are simple characters that don't need escaping, but we escape for safety
                escaped_delimiter = re.escape(actual_delimiter)
                split_result = re.split(f"({escaped_delimiter})", text)
            else:
                # Standard split without including delimiter
                split_result = text.split(actual_delimiter)

            self.parameter_output_values["output"] = split_result
            self.publish_update_to_parameter("output", split_result)
        except re.error as e:
            # Handle regex-specific errors (shouldn't occur with predefined delimiters)
            msg = f"{self.name}: Regex error while splitting text: {e}"
            logger.error(msg)
            self.parameter_output_values["output"] = []
            self.publish_update_to_parameter("output", [])
        except (TypeError, ValueError) as e:
            # Handle type or value errors
            msg = f"{self.name}: Error splitting text: {e}"
            logger.error(msg)
            self.parameter_output_values["output"] = []
            self.publish_update_to_parameter("output", [])

    def process(self) -> None:
        self._process_text()
