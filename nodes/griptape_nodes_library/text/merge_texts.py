from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class MergeTexts(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add a list of inputs
        self.add_parameter(
            Parameter(
                name="input_1",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                tooltip="Text inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_2",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                tooltip="Text inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_3",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                tooltip="Text inputs to merge together.",
            )
        )
        self.add_parameter(
            Parameter(
                name="input_4",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                tooltip="Text inputs to merge together.",
            )
        )

        # Add parameter for the separator string
        self.add_parameter(
            Parameter(
                name="merge_string",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                type="str",
                default_value="\\n\\n",
                tooltip="The string to use as separator between inputs.",
            )
        )

        # Add output parameter for the merged text
        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="The merged text result.",
            )
        )

    def process(self) -> None:
        # Get the list of input texts
        input_1 = self.parameter_values.get("input_1", None)
        input_2 = self.parameter_values.get("input_2", None)
        input_3 = self.parameter_values.get("input_3", None)
        input_4 = self.parameter_values.get("input_4", None)

        # Get the separator string and replace \n with actual newlines
        separator = self.parameter_values.get("merge_string", "\\n\\n").replace("\\n", "\n")

        # Create a list of input texts if they aren't none
        input_texts = [input_1, input_2, input_3, input_4]
        # Filter out None values from the list
        input_texts = [text for text in input_texts if text is not None]

        # Join all the inputs with the separator
        merged_text = separator.join(input_texts).strip()

        # Set the output
        self.parameter_output_values["output"] = merged_text
