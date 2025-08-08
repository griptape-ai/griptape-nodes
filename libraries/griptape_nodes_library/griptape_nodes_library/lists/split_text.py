import re
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
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
        self.delimiter_type.add_trait(Options(choices=["newlines", "space", "comma", "custom"]))

        # Add custom delimiter parameter
        self.custom_delimiter = Parameter(
            name="custom_delimiter",
            tooltip="Custom delimiter to split the text by",
            type="str",
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=" ",
        )
        self.add_parameter(self.custom_delimiter)

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
        # Keep UI behavior consistent with other nodes: show custom delimiter only when selected
        if parameter.name == "delimiter_type":
            if value == "custom":
                self.show_parameter_by_name("custom_delimiter")
            else:
                self.hide_parameter_by_name("custom_delimiter")

        if parameter.name != "output":
            self._process_text()
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception]:
        exceptions = []
        text = self.get_parameter_value("text")
        if text is None:
            exceptions.append(Exception(f"{self.name}: Text is required to split"))
        elif not isinstance(text, str):
            exceptions.append(Exception(f"{self.name}: Text must be a string"))
        delimiter_type = self.get_parameter_value("delimiter_type")
        if delimiter_type == "custom":
            delimiter = self.get_parameter_value("custom_delimiter")
            if delimiter is None:
                exceptions.append(Exception(f"{self.name}: Custom delimiter is required when delimiter type is custom"))
            elif not isinstance(delimiter, str):
                msg = f"{self.name}: Delimiter must be a string"
                exceptions.append(Exception(msg))
            else:
                # Enforce a reasonable maximum on the raw delimiter length
                max_delimiter_length = 1000
                if len(delimiter) > max_delimiter_length:
                    msg = f"{self.name}: Delimiter is too long"
                    exceptions.append(Exception(msg))
        return exceptions

    def _process_text(self) -> None:
        """Process the text input and split it according to the selected delimiter."""
        # Get the text and delimiter type from input parameters
        text = self.get_parameter_value("text")
        delimiter_type = self.get_parameter_value("delimiter_type")
        custom_delimiter = self.get_parameter_value("custom_delimiter")
        include_delimiter = self.get_parameter_value("include_delimiter")
        keep_empty = self.metadata.get("keep_empty", False)

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
                # Split and keep the delimiter (escape to avoid regex injection)
                escaped_delimiter = re.escape(actual_delimiter)
                split_result = re.split(f"({escaped_delimiter})", text)
            else:
                # Standard split without including delimiter
                split_result = text.split(actual_delimiter)

            # Optionally keep empty results; default behavior is to drop empties
            if not keep_empty:
                split_result = [item for item in split_result if item != ""]

            self.parameter_output_values["output"] = split_result
            self.publish_update_to_parameter("output", split_result)
        except (re.error, TypeError, ValueError):
            # If splitting fails, return empty list
            self.parameter_output_values["output"] = []
            self.publish_update_to_parameter("output", [])

    def process(self) -> None:
        self._process_text()
