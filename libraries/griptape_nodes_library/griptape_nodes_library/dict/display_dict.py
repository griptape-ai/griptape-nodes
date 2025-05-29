from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class DisplayDictionary(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        # Create input/output parameter group
        with ParameterGroup(name="Input/Output") as io_group:
            Parameter(
                name="dictionary",
                default_value=value,
                input_types=["dict"],
                output_type="dict",
                tooltip="The dictionary content to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        self.add_node_element(io_group)

        # Create display parameter group
        with ParameterGroup(name="Display") as display_group:
            Parameter(
                name="dictionary_display",
                default_value=str(value),
                type="str",
                tooltip="The dictionary content",
                ui_options={"multiline": True, "placeholder_text": "The dictionary content will be displayed here."},
                allowed_modes={ParameterMode.PROPERTY},
            )
        self.add_node_element(display_group)

    def process(self) -> None:
        # Simply output the default value or any updated property value
        self.parameter_output_values["dictionary_display"] = str(self.parameter_values["dictionary"])

        # Convert the dictionary to a string
        self.parameter_output_values["dictionary"] = self.parameter_values["dictionary"]
