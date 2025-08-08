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
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT},
            ui_options={"multiline": True},
        )
        self.add_parameter(self.text_input)

        # Add delimiter type parameter
        self.delimiter_type = Parameter(
            name="delimiter_type",
            tooltip="Type of delimiter to use for splitting",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="newlines",
        )
        self.add_parameter(self.delimiter_type)
        self.delimiter_type.add_trait(Options(choices=["newlines", "space", "comma", "custom"]))

        # Add custom delimiter parameter
        self.custom_delimiter = Parameter(
            name="custom_delimiter",
            tooltip="Custom delimiter to split the text by",
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=" ",
            ui_options={"hide": False},
        )
        self.add_parameter(self.custom_delimiter)

        # Add include delimiter option
        self.include_delimiter = Parameter(
            name="include_delimiter",
            tooltip="Whether to include the delimiter in the split results",
            input_types=["bool"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value=False,
        )
        self.add_parameter(self.include_delimiter)

        # Add output parameter
        self.output = Parameter(
            name="output",
            tooltip="List of text items",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name != "output":
            self._process_text()
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = []
        if self.get_parameter_value("text") is None:
            exceptions.append(Exception(f"{self.name}: Text is required to split"))
        return exceptions

    def _process_text(self) -> None:
        """Process the text input and split it according to the selected delimiter."""
        # Get the text and delimiter type from input parameters
        text = self.get_parameter_value("text")
        delimiter_type = self.get_parameter_value("delimiter_type")
        custom_delimiter = self.get_parameter_value("custom_delimiter")
        include_delimiter = self.get_parameter_value("include_delimiter")

        # Validate inputs
        if text is None or not isinstance(text, str):
            return

        # Determine the actual delimiter based on type
        if delimiter_type == "newlines":
            actual_delimiter = "\n"
        elif delimiter_type == "space":
            actual_delimiter = " "
        elif delimiter_type == "comma":
            actual_delimiter = ","
        elif delimiter_type == "custom":
            # For custom delimiter, use the custom_delimiter value
            actual_delimiter = custom_delimiter if custom_delimiter is not None else " "
        else:
            actual_delimiter = "\n"  # default to newlines

        # Split the text by the delimiter
        try:
            if include_delimiter:
                # Use a more complex approach to include delimiters
                import re

                # Escape special regex characters in the delimiter
                escaped_delimiter = re.escape(actual_delimiter)
                # Split and keep the delimiter
                split_result = re.split(f"({escaped_delimiter})", text)
                # Remove empty strings
                split_result = [item for item in split_result if item]
            else:
                # Standard split without including delimiter
                split_result = text.split(actual_delimiter)
                # Remove empty strings if they occur at the beginning or end
                split_result = [item for item in split_result if item]

            self.parameter_output_values["output"] = split_result
            self.publish_update_to_parameter("output", split_result)
        except Exception as e:
            logger.error(f"{self.name}: Error splitting text: {e}")
            # If splitting fails, return empty list
            self.parameter_output_values["output"] = []
            self.publish_update_to_parameter("output", [])

    def process(self) -> None:
        self._process_text()
