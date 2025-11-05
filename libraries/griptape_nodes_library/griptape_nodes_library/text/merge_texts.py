from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class MergeTexts(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.default_num_inputs = 4

        for i in range(self.default_num_inputs):
            self.add_parameter(
                ParameterString(
                    name=f"input_{i + 1}",
                    allow_output=False,
                    placeholder_text=f"Input {i + 1}",
                    tooltip="Text inputs to merge together.",
                )
            )
        # Add parameter for the separator string
        self.add_parameter(
            ParameterString(
                name="merge_string",
                allow_output=False,
                placeholder_text="text separator",
                default_value="\\n\\n",
                tooltip="The string to use as separator between inputs.",
            )
        )
        self.add_parameter(
            ParameterBool(
                name="whitespace",
                default_value=False,
                tooltip="Whether to trim whitespace from the merged text.",
                allow_output=False,
                on_label="trim",
                off_label="keep",
            )
        )

        # Add output parameter for the merged text
        self.add_parameter(
            ParameterString(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                multiline=True,
                placeholder_text="The merged text result.",
                tooltip="The merged text result.",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name.startswith("input_") or parameter.name in ["merge_string", "whitespace"]:
            self._merge_texts()
        return super().after_value_set(parameter, value)

    def _merge_texts(self) -> None:
        # Get the whitespace trim value
        trim_whitespace = self.get_parameter_value("whitespace")

        # Get all input texts dynamically
        input_texts = []
        for i in range(1, self.default_num_inputs + 1):
            input_value = self.get_parameter_value(f"input_{i}")
            if input_value is not None:
                text = str(input_value)
                # If trim_whitespace is True, trim the text
                if trim_whitespace:
                    text = text.strip()
                # Filter out blank inputs (after trimming if trim_whitespace is True)
                if text == "":
                    continue
                input_texts.append(text)

        # Get the separator string and replace \n with actual newlines
        # If trim_whitespace is True, use separator as-is (even if empty)
        # If trim_whitespace is False and separator is None or empty, default to \\n\\n (double newline)
        separator = self.get_parameter_value("merge_string")
        if not trim_whitespace and (separator is None or separator == ""):
            separator = "\\n\\n"
        # Replace escaped newlines with actual newlines
        if separator is not None:
            separator = separator.replace("\\n", "\n")

        # Join all the inputs with the separator
        merged_text = separator.join(input_texts)
        # Only strip the final result if trim_whitespace is True
        if trim_whitespace:
            merged_text = merged_text.strip()

        # Set the output
        self.set_parameter_value("output", merged_text)
        self.publish_update_to_parameter("output", merged_text)
        self.parameter_output_values["output"] = merged_text

    def process(self) -> None:
        # Merge the texts
        self._merge_texts()
