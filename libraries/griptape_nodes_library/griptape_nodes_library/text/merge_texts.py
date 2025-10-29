from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
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
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    placeholder_text=f"Input {i + 1}",
                    tooltip="Text inputs to merge together.",
                )
            )
        # Add parameter for the separator string
        self.add_parameter(
            ParameterString(
                name="merge_string",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                placeholder_text="\\n\\n",
                default_value="\\n\\n",
                tooltip="The string to use as separator between inputs.",
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
        if parameter.name.startswith("input_") or parameter.name == "merge_string":
            self._merge_texts()
        return super().after_value_set(parameter, value)

    def _merge_texts(self) -> None:
        # Get all input texts dynamically
        input_texts = []
        for i in range(1, self.default_num_inputs + 1):
            input_value = self.get_parameter_value(f"input_{i}")
            if input_value is not None and input_value != "":
                input_texts.append(str(input_value))

        # Get the separator string and replace \n with actual newlines
        separator = self.get_parameter_value("merge_string") or "\\n\\n"
        separator = separator.replace("\\n", "\n")

        # Join all the inputs with the separator
        merged_text = separator.join(input_texts).strip()

        # Set the output
        self.set_parameter_value("output", merged_text)
        self.publish_update_to_parameter("output", merged_text)
        self.parameter_output_values["output"] = merged_text

    def process(self) -> None:
        # Merge the texts
        self._merge_texts()
