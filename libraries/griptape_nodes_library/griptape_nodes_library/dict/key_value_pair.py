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
                name="my_key",
                input_types=["str"],
                default_value="",
                type="str",
                tooltip="Key for the dictionary",
            )
        )
        self.add_parameter(
            Parameter(
                name="my_value",
                input_types=["str"],
                default_value="",
                type="str",
                tooltip="Value for the dictionary",
            )
        )
        self.add_parameter(
            Parameter(
                name="dictionary",
                type="dict",
                default_value={"": ""},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="Dictionary containing the key-value pair",
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name in {"my_key", "my_value"}:
            new_dict = {}

            new_key = self.get_parameter_value("my_key")
            new_value = self.get_parameter_value("my_value")

            new_dict = {new_key: new_value}

            self.parameter_output_values["dictionary"] = new_dict
            self.set_parameter_value("dictionary", new_dict)
            modified_parameters_set.add("dictionary")
            self.show_parameter_by_name("dictionary")

        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        """Process the node by creating a key-value pair dictionary."""
        key = self.get_parameter_value("my_key")
        value = self.get_parameter_value("my_value")

        # Set output value
        self.parameter_output_values["dictionary"] = {key: value}
