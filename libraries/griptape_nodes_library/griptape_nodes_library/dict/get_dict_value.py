from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class DictGetValueByKey(ControlNode):
    """Get a value from a dictionary by key with optional default handling."""

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
                tooltip="Dictionary to get value from",
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
                tooltip="Key to lookup in the dictionary",
            )
        )

        # Parameter for whether to supply default if not found
        self.add_parameter(
            Parameter(
                name="supply_default_if_not_found",
                input_types=["bool"],
                type="bool",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=True,
                tooltip="If True, return default value when key not found. If False, throw exception when key not found.",
            )
        )

        # Parameter for the default value (hidden by default)
        self.add_parameter(
            Parameter(
                name="default_value_if_not_found",
                input_types=["str", "int", "float", "bool", "dict", "list"],
                type="any",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=None,
                tooltip="Default value to return when key is not found (only used if supply_default_if_not_found is True)",
                ui_options={"hide": False},  # Will be controlled by show/hide logic
            )
        )

        # Output parameter for the value
        self.add_parameter(
            Parameter(
                name="value",
                output_type="any",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=None,
                tooltip="Value found for the specified key, or default value if not found",
            )
        )

    def _update_default_visibility(self) -> None:
        """Show/hide the default value parameter based on supply_default_if_not_found."""
        supply_default = self.get_parameter_value("supply_default_if_not_found")
        if supply_default:
            self.show_parameter_by_name("default_value_if_not_found")
        else:
            self.hide_parameter_by_name("default_value_if_not_found")

    def _get_value(self) -> Any:
        """Get value from dictionary by key with default handling."""
        input_dict = self.get_parameter_value("dict")
        key = self.get_parameter_value("key")
        supply_default = self.get_parameter_value("supply_default_if_not_found")
        default_value = self.get_parameter_value("default_value_if_not_found")

        if not isinstance(input_dict, dict):
            if supply_default:
                return default_value
            msg = "Input is not a dictionary"
            raise ValueError(msg)

        if not key:
            if supply_default:
                return default_value
            msg = "Key cannot be empty"
            raise ValueError(msg)

        if key in input_dict:
            return input_dict[key]
        if supply_default:
            return default_value
        msg = f"Key '{key}' not found in dictionary"
        raise KeyError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update outputs and visibility when inputs change."""
        if parameter.name == "supply_default_if_not_found":
            self._update_default_visibility()

        if parameter.name in ["dict", "key", "supply_default_if_not_found", "default_value_if_not_found"]:
            try:
                result_value = self._get_value()
                self.parameter_output_values["value"] = result_value
                self.set_parameter_value("value", result_value)
            except Exception:
                # Don't fail during parameter setting, just clear the output
                self.parameter_output_values["value"] = None
                self.set_parameter_value("value", None)

        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Update outputs when connections change."""
        if target_parameter.name in ["dict", "key", "supply_default_if_not_found", "default_value_if_not_found"]:
            try:
                result_value = self._get_value()
                self.parameter_output_values["value"] = result_value
            except Exception:
                self.parameter_output_values["value"] = None

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        """Process the node by getting the dictionary value."""
        result_value = self._get_value()
        self.parameter_output_values["value"] = result_value
