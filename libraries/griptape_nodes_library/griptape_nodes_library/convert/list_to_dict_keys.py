from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.retained_mode.griptape_nodes import logger


class ListToDictKeys(SuccessFailureNode):
    """ListToDictKeys Node that converts a list to dictionary keys with optional values.

    This node takes a list as input and creates a dictionary using the list items as keys.
    Values can be provided programmatically via the optional 'values' parameter, or default
    to empty strings. It's perfect for dynamic form generation, template systems, or any
    scenario where you need to create key-value pairs from a list of keys.

    Key Features:
    - Converts list items to dictionary keys with optional pre-populated values
    - Optional programmatic value pre-population via 'values' parameter
    - Handles any data type by converting to string representation
    - Handles duplicate keys by numbering them (e.g., ADJECTIVE, ADJECTIVE_2, ADJECTIVE_3)
    - Preserves user-entered values when regenerating the dictionary
    - Supports both numbered duplicates and merged duplicates modes
    - Provides real-time UI updates and status tracking

    Use Cases:
    - Mad Libs style applications
    - Dynamic form generation
    - Template variable collection
    - User input collection systems

    Examples:
    Basic usage (empty values):
    Input keys: ["ADJECTIVE", "NOUN", "ADJECTIVE", "VERB"]
    Output: {"ADJECTIVE": "", "NOUN": "", "ADJECTIVE_2": "", "VERB": ""}

    With programmatic values (positional matching):
    Input keys: ["name", "email", "age"]
    Input values: ["John", "john@example.com", "25"]
    Output: {"name": "John", "email": "john@example.com", "age": "25"}

    With partial values (fewer values than keys):
    Input keys: ["one", "two", "three"]
    Input values: ["happy", "sad"]
    Output: {"one": "happy", "two": "sad", "three": ""}

    Mixed data types:
    Input keys: ["name", 42, True, None, "age"]
    Output: {"name": "", "42": "", "True": "", "None": "", "age": ""}

    Numbers:
    Input: [1, 2, 3, 1, 4]
    Output: {"1": "", "2": "", "3": "", "1_2": "", "4": ""}

    Note: The first occurrence uses the original key name, subsequent duplicates are numbered starting from _2.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the ListToDictKeys node with all required parameters.

        This method sets up the node's input/output parameters and internal state tracking.
        It also checks for existing KeyValuePairs data to restore the UI state on reload.
        """
        super().__init__(name, metadata)
        logger.debug(f"{self.name}: Initializing node")

        # Input parameter for the list of keys
        # This is the primary input that drives the dictionary generation
        self.keys = Parameter(
            name="keys",
            input_types=["list"],
            type="list",
            allowed_modes={ParameterMode.INPUT},
            tooltip="List of keys to create parameters for",
        )
        self.add_parameter(self.keys)

        # Optional input parameter for pre-defined values
        # This allows developers to programmatically provide values for keys
        self.optional_values = Parameter(
            name="optional_values",
            input_types=["list"],
            type="list",
            allowed_modes={ParameterMode.INPUT},
            default_value=None,
            tooltip="Optional list of values to pre-populate the dictionary (matched by position/order)",
        )
        self.add_parameter(self.optional_values)

        # Parameter to control duplicate handling
        # When True: duplicates are numbered (ADJECTIVE, ADJECTIVE_2, ADJECTIVE_3)
        # When False: duplicates are merged (only unique keys kept)
        self.maintain_duplicates = ParameterBool(
            name="maintain_duplicates",
            allow_output=False,
            default_value=True,
            tooltip="If True, duplicate keys will be numbered (e.g., ADJECTIVE, ADJECTIVE_2, ADJECTIVE_3). If False, duplicates will be merged.",
        )
        self.add_parameter(self.maintain_duplicates)

        # Output parameter for the generated key-value pairs
        # This is the main output that contains the dictionary with user-editable values
        self.key_value_pairs = Parameter(
            name="KeyValuePairs",
            type="dict",
            allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            default_value={},
            tooltip="Dictionary of key-value pairs",
            ui_options={"hide_property": False},
        )
        self.add_parameter(self.key_value_pairs)

        # Add status parameters using the helper method
        # These provide success/failure feedback and detailed result information
        self._create_status_parameters(
            result_details_tooltip="Details about the list-to-dict conversion result",
            result_details_placeholder="Details on the key-value pair generation will be presented here.",
            parameter_group_initially_collapsed=False,
        )

        # Internal state tracking for user value preservation
        # _user_values: stores user-entered values to preserve them during regeneration
        # _updating_generated_list: prevents infinite loops during parameter updates
        self._user_values = {}
        self._updating_generated_list = False

        # Check if we have existing KeyValuePairs data and refresh the UI
        # This ensures that when a workflow is loaded, the UI displays the saved values
        try:
            existing_kvp = self.get_parameter_value("KeyValuePairs")
        except (AttributeError, KeyError) as e:
            logger.debug(f"{self.name}: No existing KeyValuePairs data: {e}")
            return

        if not existing_kvp or not isinstance(existing_kvp, dict) or not existing_kvp:
            return

        # SUCCESS PATH AT END - Restore UI state with existing data
        logger.debug(f"{self.name}: Found existing KeyValuePairs data: {existing_kvp}")
        self.publish_update_to_parameter("KeyValuePairs", existing_kvp)

    def process(self) -> None:
        """Process the node by updating the key-value pairs.

        This is the main execution method that:
        1. Resets the execution state and sets failure defaults
        2. Attempts to update the key-value pairs based on current input
        3. Handles any errors that occur during processing
        4. Sets success status with detailed result information

        The method follows the SuccessFailureNode pattern with proper error handling
        and status reporting for a professional user experience.
        """
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        logger.debug(f"ListToDictKeys.process(): Called for node {self.name}")

        # FAILURE CASES FIRST - Attempt to update key-value pairs
        try:
            self._update_key_value_pairs(delete_excess_parameters=True)
        except Exception as e:
            error_details = f"Failed to update key-value pairs: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            msg = f"{self.name}: {error_details}"
            logger.error(msg)
            self._handle_failure_exception(e)
            return

        # SUCCESS PATH AT END - Set success status with detailed information
        success_details = self._get_success_message()
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        logger.debug(f"ListToDictKeys '{self.name}': {success_details}")

    def _update_key_value_pairs(self, *, delete_excess_parameters: bool = False) -> None:
        """Update the key-value pairs based on current input keys.

        This is the core method that orchestrates the entire key-value pair generation process.
        It handles duplicate call prevention, key validation, user value preservation,
        and parameter updates to ensure a smooth user experience.

        Args:
            delete_excess_parameters:   If True, delete parameters when key list is shorter.
                                        If False, keep existing parameters even when key list is shorter.
        """
        # Prevent duplicate calls to avoid infinite loops during parameter updates
        if self._updating_generated_list:
            logger.debug(f"{self.name}: Already updating, skipping duplicate call")
            return

        self._updating_generated_list = True

        # Get and validate key list from input parameter
        key_list = self._get_key_list()
        if key_list is None:
            logger.debug(f"{self.name}: No valid key list found, skipping update")
            self._updating_generated_list = False
            return

        logger.debug(f"{self.name}: Processing key list: {key_list}")

        # Get optional values list for programmatic pre-population
        values_list = self.get_parameter_value("optional_values")
        provided_values = {}
        if values_list and isinstance(values_list, list):
            logger.debug(f"{self.name}: Using provided values for {len(values_list)} keys: {values_list}")
            # Match values by position/index, not by key name
            for i, value in enumerate(values_list):
                if i < len(key_list):
                    provided_values[i] = str(value)  # Store by index position
            logger.debug(f"{self.name}: Mapped values by position: {provided_values}")
        else:
            logger.debug(f"{self.name}: No values provided or values is not a list")

        # Generate fresh key-value pairs from the validated key list with provided values
        key_value_pairs = self._generate_key_value_pairs(key_list, provided_values)

        # Preserve user values ONLY for keys that exist in the new key list and don't have provided values
        key_value_pairs = self._preserve_user_values_for_new_keys(key_value_pairs, provided_values)

        # Only delete excess parameters if explicitly requested (e.g., during process())
        if delete_excess_parameters:
            self._delete_excess_parameters(len(key_value_pairs))

        # Update or create parameters with the final key-value dictionary
        self._update_parameters(key_value_pairs)

        self._updating_generated_list = False

    def _get_key_list(self) -> list | None:
        """Get and validate the key list from input parameter."""
        # FAILURE CASES FIRST
        try:
            key_list = self.get_parameter_value("keys")
            logger.debug(f"{self.name}: Retrieved keys from parameter: {key_list}")
        except (AttributeError, KeyError) as e:
            logger.debug(f"{self.name}: Error getting keys: {e}")
            self._clear_list()
            return None

        if not isinstance(key_list, list):
            logger.debug(f"{self.name}: Keys is not a list: {type(key_list)}")
            self._clear_list()
            return None

        if len(key_list) == 0:
            logger.debug(f"{self.name}: Keys list is empty")
            self._clear_list()
            return None

        # SUCCESS PATH AT END
        logger.debug(f"{self.name}: Retrieved keys: {key_list}")
        logger.debug(f"{self.name}: Valid keys list with {len(key_list)} items")
        return key_list

    def _generate_key_value_pairs(
        self, key_list: list, provided_values: dict[int, str] | None = None
    ) -> dict[str, str]:
        """Generate key-value pairs from the key list with optional provided values."""
        logger.debug(f"{self.name}: Processing {len(key_list)} keys: {key_list}")

        # Get the maintain_duplicates setting
        maintain_duplicates = self.get_parameter_value("maintain_duplicates")
        if maintain_duplicates is None:
            maintain_duplicates = True

        if maintain_duplicates:
            return self._generate_with_duplicates(key_list, provided_values)
        return self._generate_without_duplicates(key_list, provided_values)

    def _generate_with_duplicates(
        self, key_list: list, provided_values: dict[int, str] | None = None
    ) -> dict[str, str]:
        """Generate key-value pairs with duplicate numbering."""
        key_value_dict = {}
        key_counts = {}

        for i, key in enumerate(key_list):
            key_str = str(key).strip()
            if not key_str:
                continue

            # Count occurrences of this key
            if key_str not in key_counts:
                key_counts[key_str] = 0
            key_counts[key_str] += 1

            # Generate unique key name for duplicates
            if key_counts[key_str] == 1:
                unique_key = key_str
            else:
                unique_key = f"{key_str}_{key_counts[key_str]}"

            # Use provided value by index position if available, otherwise use empty string
            if provided_values and i in provided_values:
                key_value_dict[unique_key] = provided_values[i]
            else:
                key_value_dict[unique_key] = ""

        logger.debug(f"{self.name}: Generated {len(key_value_dict)} key-value pairs with duplicates")
        return key_value_dict

    def _generate_without_duplicates(
        self, key_list: list, provided_values: dict[int, str] | None = None
    ) -> dict[str, str]:
        """Generate key-value pairs without duplicates (merge mode)."""
        key_value_dict = {}

        for i, key in enumerate(key_list):
            key_str = str(key).strip()
            if not key_str:
                continue

            # Use provided value by index position if available, otherwise use empty string
            if provided_values and i in provided_values:
                key_value_dict[key_str] = provided_values[i]
            else:
                key_value_dict[key_str] = ""

        logger.debug(f"{self.name}: Generated {len(key_value_dict)} key-value pairs without duplicates")
        return key_value_dict

    def _preserve_user_values(self, key_value_dict: dict[str, str]) -> dict[str, str]:
        """Preserve user values for matching keys."""
        # FAILURE CASES FIRST
        try:
            existing_kvp = self.get_parameter_value("KeyValuePairs")
        except (AttributeError, KeyError) as e:
            logger.warning(f"ListToDictKeys._preserve_user_values(): Error getting existing KeyValuePairs: {e}")
            return self._fallback_to_saved_values(key_value_dict)

        if not existing_kvp or not isinstance(existing_kvp, dict):
            return self._fallback_to_saved_values(key_value_dict)

        # SUCCESS PATH AT END - Only preserve values for keys that exist in the new key list
        preserved_count = 0
        for key_name in key_value_dict:
            if key_name in existing_kvp and existing_kvp[key_name] and str(existing_kvp[key_name]).strip():
                key_value_dict[key_name] = str(existing_kvp[key_name])
                preserved_count += 1
                logger.debug(f"{self.name}: Preserved user value for '{key_name}': '{existing_kvp[key_name]}'")

        if preserved_count > 0:
            logger.debug(f"{self.name}: Preserved {preserved_count} user values")
        else:
            logger.debug(f"{self.name}: No matching user values to preserve")

        return key_value_dict

    def _preserve_user_values_selectively(
        self, key_value_dict: dict[str, str], provided_values: dict[int, str]
    ) -> dict[str, str]:
        """Preserve user values only for keys that don't have provided values."""
        # FAILURE CASES FIRST
        try:
            existing_kvp = self.get_parameter_value("KeyValuePairs")
        except (AttributeError, KeyError) as e:
            logger.debug(f"{self.name}: Error getting existing KeyValuePairs: {e}")
            return self._fallback_to_saved_values(key_value_dict)

        if not existing_kvp or not isinstance(existing_kvp, dict):
            logger.debug(f"{self.name}: No existing KeyValuePairs to preserve")
            return self._fallback_to_saved_values(key_value_dict)

        # SUCCESS PATH AT END - Only preserve values for keys that don't have provided values
        preserved_count = 0
        for i, (key_name, current_value) in enumerate(key_value_dict.items()):
            # Skip if this key has a provided value (provided values take precedence)
            if i in provided_values:
                logger.debug(f"{self.name}: Skipping preservation for '{key_name}' - has provided value")
                continue

            # Only preserve if the existing value is not empty and different from current
            if (
                key_name in existing_kvp
                and existing_kvp[key_name]
                and str(existing_kvp[key_name]).strip()
                and existing_kvp[key_name] != current_value
            ):
                key_value_dict[key_name] = str(existing_kvp[key_name])
                preserved_count += 1
                logger.debug(f"{self.name}: Preserved user value for '{key_name}': '{existing_kvp[key_name]}'")

        if preserved_count > 0:
            logger.debug(f"{self.name}: Preserved {preserved_count} user values")
        else:
            logger.debug(f"{self.name}: No user values to preserve (all have provided values or are empty)")

        return key_value_dict

    def _preserve_user_values_for_new_keys(
        self, key_value_dict: dict[str, str], provided_values: dict[int, str]
    ) -> dict[str, str]:
        """Preserve user values only for keys that exist in the new key list and don't have provided values."""
        # FAILURE CASES FIRST
        try:
            existing_kvp = self.get_parameter_value("KeyValuePairs")
        except (AttributeError, KeyError) as e:
            logger.debug(f"{self.name}: Error getting existing KeyValuePairs: {e}")
            return key_value_dict

        if not existing_kvp or not isinstance(existing_kvp, dict):
            logger.debug(f"{self.name}: No existing KeyValuePairs to preserve")
            return key_value_dict

        # SUCCESS PATH AT END - Only preserve values for keys that exist in the new key list and don't have provided values
        preserved_count = 0
        for i, (key_name, current_value) in enumerate(key_value_dict.items()):
            # Skip if this key has a provided value (provided values take precedence)
            if i in provided_values:
                logger.debug(f"{self.name}: Skipping preservation for '{key_name}' - has provided value")
                continue

            # Only preserve if the key exists in existing KeyValuePairs and has a non-empty value
            if (
                key_name in existing_kvp
                and existing_kvp[key_name]
                and str(existing_kvp[key_name]).strip()
                and existing_kvp[key_name] != current_value
            ):
                key_value_dict[key_name] = str(existing_kvp[key_name])
                preserved_count += 1
                logger.debug(f"{self.name}: Preserved user value for '{key_name}': '{existing_kvp[key_name]}'")

        if preserved_count > 0:
            logger.debug(f"{self.name}: Preserved {preserved_count} user values")
        else:
            logger.debug(f"{self.name}: No user values to preserve")

        return key_value_dict

    def _fallback_to_saved_values(self, key_value_dict: dict[str, str]) -> dict[str, str]:
        """Fallback to saved user values when parameter lookup fails."""
        if not self._user_values:
            return key_value_dict

        existing_dict = self._user_values if isinstance(self._user_values, dict) else {}

        for key_name in key_value_dict:
            if key_name in existing_dict:
                key_value_dict[key_name] = existing_dict[key_name]

        return key_value_dict

    def _get_success_message(self) -> str:
        """Generate success message with key-value pair details."""
        try:
            kvp = self.get_parameter_value("KeyValuePairs")
            if kvp and isinstance(kvp, dict):
                key_count = len(kvp)
                non_empty_values = sum(1 for v in kvp.values() if v and str(v).strip())
                return f"Successfully generated {key_count} key-value pairs ({non_empty_values} with values)"
        except Exception as e:
            logger.warning(f"ListToDictKeys._get_success_message(): Error getting KeyValuePairs: {e}")
        return "Successfully generated key-value pairs from input list"

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["KeyValuePairs"] = {}

    def _save_user_values(self) -> None:
        """Save current user values from the KeyValuePairs parameter."""
        # FAILURE CASES FIRST
        self._user_values = {}

        try:
            kv_dict = self.get_parameter_value("KeyValuePairs")
        except (AttributeError, KeyError) as e:
            logger.debug(f"{self.name}: Error getting KeyValuePairs: {e}")
            return

        if not kv_dict or not isinstance(kv_dict, dict):
            return

        # SUCCESS PATH AT END
        self._user_values = kv_dict.copy()

    def _update_parameters(self, key_value_dict: dict[str, str]) -> None:
        """Update the KeyValuePairs parameter with the key-value dictionary."""
        logger.debug(f"{self.name}: Setting KeyValuePairs to {len(key_value_dict)} items")
        logger.debug(f"{self.name}: Key-value pairs: {key_value_dict}")

        # Clear the old parameter first to ensure clean update
        self._clear_list()

        # Set the parameter value to the key-value dictionary
        self.set_parameter_value("KeyValuePairs", key_value_dict)
        self.publish_update_to_parameter("KeyValuePairs", key_value_dict)
        self.parameter_output_values["KeyValuePairs"] = key_value_dict

        logger.debug(f"{self.name}: Set KeyValuePairs parameter with {len(key_value_dict)} items")

    def _delete_excess_parameters(self, new_count: int) -> None:
        """Delete parameters when the new list is shorter than the current parameter count."""
        # This is handled by the _update_parameters method now

    def _clear_list(self) -> None:
        """Clear the KeyValuePairs parameter."""
        self.set_parameter_value("KeyValuePairs", {})
        self.publish_update_to_parameter("KeyValuePairs", {})
        self.parameter_output_values["KeyValuePairs"] = {}
        self._user_values = {}

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update key-value pairs when a value is assigned to the keys or values parameter."""
        logger.debug(f"{self.name}: after_value_set called for parameter: {parameter.name} with value: {value}")
        if parameter in (self.keys, self.optional_values):
            logger.debug(f"{self.name}: Triggering _update_key_value_pairs due to {parameter.name} change")
            self._update_key_value_pairs()
        elif parameter == self.key_value_pairs and isinstance(value, dict):
            # User modified the KeyValuePairs dictionary directly - save their changes
            logger.debug(f"{self.name}: User modified KeyValuePairs directly, saving values")
            self._user_values = value.copy()

        return super().after_value_set(parameter, value)

    def after_incoming_connection_removed(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        """Update key-value pairs when incoming connection is removed."""
        self._update_key_value_pairs()
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)
