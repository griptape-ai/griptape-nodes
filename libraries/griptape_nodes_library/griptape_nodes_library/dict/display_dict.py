from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class DisplayDictionary(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        # Add output parameter for the string
        self.add_parameter(
            Parameter(
                name="dictionary",
                default_value=value,
                input_types=["dict"],
                output_type="dict",
                tooltip="The dictionary content to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="dictionary_display",
                default_value=str(value),
                type="str",
                tooltip="The dictionary content",
                ui_options={"multiline": True, "placeholder_text": "The dictionary content will be displayed here."},
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if target_parameter.name == "dictionary":
            self.set_parameter_to_default_value(target_parameter.name)
            modified_parameters_set.add(target_parameter.name)

        return super().after_incoming_connection_removed(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def process(self) -> None:
        # Simply output the default value or any updated property value
        self.parameter_output_values["dictionary_display"] = str(self.parameter_values["dictionary"])

        # Convert the dictionary to a string
        self.parameter_output_values["dictionary"] = self.parameter_values["dictionary"]
