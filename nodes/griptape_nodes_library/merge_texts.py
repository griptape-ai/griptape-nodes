from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


class MergeTextsNode(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add a parameter that accepts a list of strings for text inputs
        self.add_parameter(
            Parameter(
                name="texts",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["list"],  # This parameter accepts lists
                default_value=[],
                tooltip="List of texts to merge",
            )
        )

        # Add separator parameter
        self.add_parameter(
            Parameter(
                name="separator",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["str"],
                default_value="\n",
                tooltip="Separator to use between texts",
            )
        )

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="The merged text",
            )
        )

    def process(self) -> None:
        # Get the list of input texts
        input_texts = self.parameter_values.get("texts", [])

        # Convert to list if it's not already (handling potential single value)
        if not isinstance(input_texts, list):
            input_texts = [input_texts] if input_texts is not None else []

        # Get the separator string and replace \n with actual newlines
        separator = self.parameter_values.get("separator", "\n").replace("\\n", "\n")

        # Convert all inputs to strings and filter out None values
        input_values = [str(value) for value in input_texts if value is not None]

        # Join all the inputs with the separator
        merged_text = separator.join(input_values).strip()

        # Set the output
        self.parameter_output_values["output"] = merged_text
