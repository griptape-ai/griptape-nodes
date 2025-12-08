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

    def _update_output(self) -> None:
        """Update the output parameters."""
        dictionary = self.get_parameter_value("dictionary")
        self.parameter_output_values["dictionary_display"] = str(dictionary)
        self.parameter_output_values["dictionary"] = dictionary

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "dictionary":
            self._update_output()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
