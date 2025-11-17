import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterType, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.connection_events import DeleteConnectionRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.utils.type_utils import infer_type_from_value


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
        self.output_value = Parameter(
            name="value",
            output_type="any",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=None,
            tooltip="Value found for the specified key, or default value if not found",
        )
        self.add_parameter(self.output_value)

    def _update_default_visibility(self) -> None:
        """Show/hide the default value parameter based on supply_default_if_not_found."""
        supply_default = self.get_parameter_value("supply_default_if_not_found")
        if supply_default:
            self.show_parameter_by_name("default_value_if_not_found")
        else:
            self.hide_parameter_by_name("default_value_if_not_found")

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to normalize invalid values before they hit parameter converters."""
        # Normalize invalid values before calling parent set_parameter_value
        if param_name == "key" and value is not None and value != "" and not isinstance(value, str):
            value = ""
        elif param_name == "dict" and value is not None and not isinstance(value, dict):
            value = {}

        return super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:  # noqa: PLR0911
        """Normalize invalid parameter values to prevent errors during parameter setting."""
        if parameter.name == "key":
            # If value is None or empty string, allow it through
            if value is None or value == "":
                return value
            # If value is not a string, convert to empty string to prevent validation errors
            if not isinstance(value, str):
                return ""
            return value

        if parameter.name == "dict":
            # If value is None, allow it through
            if value is None:
                return value
            # If value is not a dict, convert to empty dict to prevent validation errors
            if not isinstance(value, dict):
                return {}
            return value

        return value

    def _get_value(self) -> Any:
        """Get value from dictionary by key with default handling."""
        input_dict = self.get_parameter_value("dict")
        key = self.get_parameter_value("key")
        supply_default = self.get_parameter_value("supply_default_if_not_found")
        default_value = self.get_parameter_value("default_value_if_not_found")

        # If key is None or empty, return None (no error)
        if key is None or key == "":
            return None

        # Validate input_dict type
        if not isinstance(input_dict, dict):
            if supply_default:
                return default_value
            msg = f"{self.name}: Input is not a dictionary (got {type(input_dict).__name__})"
            raise ValueError(msg)

        # Validate key type
        if not isinstance(key, str):
            if supply_default:
                return default_value
            msg = f"{self.name}: Key must be a string, got {type(key).__name__}: {key}"
            raise TypeError(msg)

        # Success path: look up key in dictionary
        if key in input_dict:
            return input_dict[key]

        # Key not found - return default or raise error
        if supply_default:
            return default_value
        msg = f"{self.name}: Key '{key}' not found in dictionary"
        raise KeyError(msg)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update outputs and visibility when inputs change."""
        if parameter.name == "supply_default_if_not_found":
            self._update_default_visibility()

        # Check if key is None or empty - if so, don't try to evaluate anything
        key = self.get_parameter_value("key")
        if key is None or key == "":
            self.parameter_output_values["value"] = None
            self.parameter_values["value"] = None
            self.output_value.output_type = ParameterTypeBuiltin.ALL.value
            return super().after_value_set(parameter, value)

        if parameter.name in ["dict", "key", "supply_default_if_not_found", "default_value_if_not_found"]:
            try:
                result_value = self._get_value()
                self.parameter_output_values["value"] = result_value
                self.parameter_values["value"] = result_value
            except (ValueError, TypeError, KeyError):
                # Don't fail during parameter setting, just clear the output
                self.parameter_output_values["value"] = None
                self.parameter_values["value"] = None
        self._update_output_type()

        return super().after_value_set(parameter, value)

    def _update_output_type(self) -> None:
        """Update the type of the output parameter based on the type of the value."""
        logger = logging.getLogger("griptape_nodes")

        # Check if key is None or empty - if so, don't try to evaluate anything
        key = self.get_parameter_value("key")
        if key is None or key == "":
            new_output_type = ParameterTypeBuiltin.ALL.value
            self.output_value.output_type = new_output_type
            self._validate_and_remove_incompatible_connections(new_output_type)
            return

        # Try to get value and infer type
        result_value = None
        try:
            result_value = self._get_value()
        except (ValueError, TypeError, KeyError) as err:
            # If getting value fails, log and use default type
            logger.warning(
                "%s: Failed to get value for type inference. Error: %s. Using default type.",
                self.name,
                err,
            )
            new_output_type = ParameterTypeBuiltin.ALL.value
            self.output_value.output_type = new_output_type
            self._validate_and_remove_incompatible_connections(new_output_type)
            return

        # Success path: infer type from value
        try:
            inferred_type = infer_type_from_value(result_value)
            if result_value is not None:
                new_output_type = inferred_type
            else:
                new_output_type = ParameterTypeBuiltin.ALL.value
            self.output_value.output_type = new_output_type
            self._validate_and_remove_incompatible_connections(new_output_type)
        except Exception as err:
            # If type inference fails, log and use default type
            value_type = type(result_value).__name__ if result_value is not None else "unknown"
            logger.warning(
                "%s: Failed to infer output type from value (type: %s). Error: %s. Using default type.",
                self.name,
                value_type,
                err,
            )
            new_output_type = ParameterTypeBuiltin.ALL.value
            self.output_value.output_type = new_output_type
            self._validate_and_remove_incompatible_connections(new_output_type)

    def _validate_and_remove_incompatible_connections(self, new_output_type: str) -> None:
        """Validate and remove incompatible outgoing connections when output type changes.

        Args:
            new_output_type: The new output type that was set
        """
        logger = logging.getLogger("griptape_nodes")

        # Get outgoing connections from the output parameter
        connections = GriptapeNodes.FlowManager().get_connections()
        outgoing_for_node = connections.outgoing_index.get(self.name, {})
        connection_ids = outgoing_for_node.get("value", [])

        if not connection_ids:
            return

        # Validate type compatibility and remove incompatible connections
        for connection_id in connection_ids:
            if connection_id not in connections.connections:
                continue

            connection = connections.connections[connection_id]
            target_param = connection.target_parameter
            target_node = connection.target_node

            # Check if target parameter accepts the new output type
            is_compatible = any(
                ParameterType.are_types_compatible(new_output_type, input_type)
                for input_type in target_param.input_types
            )

            if not is_compatible:
                logger.info(
                    "Removing incompatible connection: %s '%s' value (%s) to '%s.%s' (accepts: %s)",
                    self.__class__.__name__,
                    self.name,
                    new_output_type,
                    target_node.name,
                    target_param.name,
                    target_param.input_types,
                )

                # Remove the incompatible connection
                delete_result = GriptapeNodes.handle_request(
                    DeleteConnectionRequest(
                        source_node_name=self.name,
                        source_parameter_name="value",
                        target_node_name=target_node.name,
                        target_parameter_name=target_param.name,
                    )
                )

                if not delete_result.succeeded():
                    logger.error(
                        "Failed to delete incompatible connection from %s.%s to %s.%s: %s",
                        self.name,
                        "value",
                        target_node.name,
                        target_param.name,
                        delete_result.result_details,
                    )

    def process(self) -> None:
        """Process the node by getting the dictionary value."""
        result_value = self._get_value()
        self._update_output_type()
        self.parameter_output_values["value"] = result_value
