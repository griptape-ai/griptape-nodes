from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class JoinText(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.default_num_inputs = 2

        self.text_parameter = ParameterList(
            name="text",
            type="str",
            input_types=["Any"],
            tooltip="Text inputs to join together.",
        )
        self.add_parameter(self.text_parameter)

        # Add parameter for the separator string
        self.add_parameter(
            ParameterString(
                name="join_string",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                placeholder_text="text separator",
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
        if parameter.parent_container_name == "text" or parameter.name == "join_string":
            self._merge_texts()
        return super().after_value_set(parameter, value)

    def _merge_texts(self) -> None:
        # Get all input texts dynamically
        texts = self.get_parameter_value("text")
        if texts is not None and texts != "":
            texts = [str(text) for text in texts]
        else:
            texts = []

        # Get the separator string and replace \n with actual newlines
        separator = self.get_parameter_value("join_string")
        if separator is None:
            separator = "\\n\\n"
        separator = separator.replace("\\n", "\n")

        # Join all the inputs with the separator
        merged_text = separator.join(texts).strip()

        # Set the output
        self.set_parameter_value("output", merged_text)
        self.publish_update_to_parameter("output", merged_text)
        self.parameter_output_values["output"] = merged_text

    def process(self) -> None:
        # Merge the texts
        self._merge_texts()
