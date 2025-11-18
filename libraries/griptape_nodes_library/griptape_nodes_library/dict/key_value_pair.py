from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class KeyValuePair(DataNode):
    """Create a Key Value Pair."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add dictionary output parameter
        self.add_parameter(
            Parameter(
                name="key",
                input_types=["str"],
                default_value="",
                type="str",
                tooltip="Key for the dictionary",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="value",
                input_types=["str", "int", "float", "bool"],
                default_value="",
                type="str",
                tooltip="Value for the dictionary",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="dictionary",
                type="dict",
                default_value={"key": "value"},
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Dictionary containing the key-value pair",
                ui_options={"display_name": "Key/Value Pair"},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name in {"key", "value"}:
            new_dict = {}

            new_key = self.get_parameter_value("key")
            new_value = self.get_parameter_value("value")

            new_dict = {new_key: new_value}

            self.parameter_output_values["dictionary"] = new_dict
            self.set_parameter_value("dictionary", new_dict)
            self.show_parameter_by_name("dictionary")

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by creating a key-value pair dictionary."""
        key = self.get_parameter_value("key")
        value = self.get_parameter_value("value")

        # Set output value
        self.parameter_output_values["dictionary"] = {key: value}
