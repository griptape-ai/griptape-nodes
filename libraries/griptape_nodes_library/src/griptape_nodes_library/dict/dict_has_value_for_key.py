from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class DictHasValueForKey(DataNode):
    """Check if a dictionary has a value for a specific key."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Input parameter for the dictionary
        self.add_parameter(
            Parameter(
                name="dict",
                input_types=["dict"],
                type="dict",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value={},
                tooltip="Dictionary to check for key",
            )
        )

        # Input parameter for the key
        self.add_parameter(
            Parameter(
                name="key",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                tooltip="Key to check for in the dictionary",
            )
        )

        # Output parameter for whether key exists
        self.add_parameter(
            Parameter(
                name="has_key",
                output_type="bool",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=False,
                tooltip="True if the key exists in the dictionary, False otherwise",
                ui_options={"hide_property": True},
            )
        )

    def _has_key(self) -> bool:
        """Check if dictionary has the specified key."""
        input_dict = self.get_parameter_value("dict")
        key = self.get_parameter_value("key")

        if not isinstance(input_dict, dict) or not key:
            return False

        return key in input_dict

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update outputs when inputs change."""
        if parameter.name in ["dict", "key"]:
            has_key = self._has_key()

            # Set output values
            self.parameter_output_values["has_key"] = has_key
            self.set_parameter_value("has_key", has_key)

            # Show the output parameter
            self.show_parameter_by_name("has_key")

        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Update outputs when connections change."""
        if target_parameter.name in ["dict", "key"]:
            has_key = self._has_key()
            self.parameter_output_values["has_key"] = has_key

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        """Process the node by checking if the dictionary has the key."""
        has_key = self._has_key()
        self.parameter_output_values["has_key"] = has_key
