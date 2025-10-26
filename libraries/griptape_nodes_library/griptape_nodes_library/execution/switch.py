from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMessage,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes.retained_mode.events.connection_events import DeleteConnectionRequest
from griptape_nodes.retained_mode.events.parameter_events import GetConnectionsForParameterRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class Switch(ControlNode):
    """A control flow node that routes execution based on matching case values.

    Compares a test value against a list of cases and directs control flow
    to the matching case's output. If no match is found, routes to the
    "No Match" control output.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata, output_control_name="No Match")

        # Initialize destination for control flow routing
        self.destination_control_flow = None

        # Add explanatory message
        self.add_node_element(
            ParameterMessage(
                name="switch_info",
                variant="info",
                value="Connect a value to test, then add cases. If the value to test matches one of the cases, it will route control to the case's connected node. If no cases match, 'No Match' will be taken.",
            )
        )

        # value_to_test parameter
        self.value_to_test = Parameter(
            name="value_to_test",
            tooltip="Value to compare against cases",
            input_types=[ParameterTypeBuiltin.ANY],
            type=ParameterTypeBuiltin.ANY,
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.value_to_test)

        # cases ParameterList - restore locked type from metadata if it exists
        cases_locked_type = metadata.get("cases_locked_type") if metadata else None
        initial_type = cases_locked_type if cases_locked_type else ParameterTypeBuiltin.ANY
        self.cases = ParameterList(
            name="cases",
            tooltip="Case values to match against",
            type=initial_type,
            input_types=[initial_type] if initial_type else [ParameterTypeBuiltin.ANY],
            output_type=ParameterTypeBuiltin.CONTROL_TYPE.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.cases)

        # Hide the cases list initially (will be shown when value_to_test is connected)
        self.cases.hide = True

    def _get_case_display_name(self, case_param: Parameter, fallback_index: int) -> str:
        """Get user-friendly display name for a case parameter.

        Args:
            case_param: The case parameter
            fallback_index: The 1-based index to use if no display_name exists

        Returns:
            Display name if available, otherwise "case {index}"
        """
        if case_param.ui_options and "display_name" in case_param.ui_options:
            return case_param.ui_options["display_name"]
        return f"case {fallback_index}"

    def _clear_all_case_connections_and_parameters(self) -> None:
        """Remove all connections from case parameters, then clear the list."""
        # Iterate through all case child parameters
        for index, case_param in enumerate(self.cases.get_child_parameters()):
            # Get connections for this parameter
            result = GriptapeNodes().handle_request(
                GetConnectionsForParameterRequest(parameter_name=case_param.name, node_name=self.name)
            )

            if not result.succeeded():
                case_name = self._get_case_display_name(case_param, index + 1)
                msg = f"Node '{self.name}': Failed to get connections for {case_name}"
                raise RuntimeError(msg)

            # Remove incoming connections
            for incoming_conn in result.incoming_connections:
                delete_result = GriptapeNodes().handle_request(
                    DeleteConnectionRequest(
                        source_node_name=incoming_conn.source_node_name,
                        source_parameter_name=incoming_conn.source_parameter_name,
                        target_node_name=self.name,
                        target_parameter_name=case_param.name,
                    )
                )
                if not delete_result.succeeded():
                    case_name = self._get_case_display_name(case_param, index + 1)
                    msg = f"Node '{self.name}': Failed to delete incoming connection from '{incoming_conn.source_node_name}.{incoming_conn.source_parameter_name}' to {case_name}"
                    raise RuntimeError(msg)

            # Remove outgoing connections
            for outgoing_conn in result.outgoing_connections:
                delete_result = GriptapeNodes().handle_request(
                    DeleteConnectionRequest(
                        source_node_name=self.name,
                        source_parameter_name=case_param.name,
                        target_node_name=outgoing_conn.target_node_name,
                        target_parameter_name=outgoing_conn.target_parameter_name,
                    )
                )
                if not delete_result.succeeded():
                    case_name = self._get_case_display_name(case_param, index + 1)
                    msg = f"Node '{self.name}': Failed to delete outgoing connection from {case_name} to '{outgoing_conn.target_node_name}.{outgoing_conn.target_parameter_name}'"
                    raise RuntimeError(msg)

        # Now clear the parameter list
        self.cases.clear_list()

        # Clear locked type and persist
        self.metadata["cases_locked_type"] = None

        # Hide the cases list after clearing
        self.cases.hide = True

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle incoming connections to value_to_test."""
        if target_parameter is self.value_to_test:
            source_type = source_parameter.output_type or source_parameter.type

            # If type changed from current locked type, clear all cases
            current_locked_type = self.metadata.get("cases_locked_type")
            if current_locked_type and current_locked_type != source_type:
                self._clear_all_case_connections_and_parameters()

            # Update locked type and persist to metadata
            self.metadata["cases_locked_type"] = source_type

            # Update cases to accept the new type
            self.cases.input_types = [source_type]
            self.cases.type = source_type

            # Show the cases list now that value_to_test is connected
            self.cases.hide = False

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle removal of incoming connections from value_to_test."""
        if target_parameter is self.value_to_test:
            # Reset value_to_test to accept ANY
            self.value_to_test.input_types = [ParameterTypeBuiltin.ANY]
            self.value_to_test.type = ParameterTypeBuiltin.ANY

            # DON'T clear cases - user might be swapping connections
            # Keep the locked type so cases stay consistent

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate connections before workflow execution."""
        exceptions = []

        # Check 1: value_to_test has incoming connection
        result = GriptapeNodes().handle_request(
            GetConnectionsForParameterRequest(parameter_name="value_to_test", node_name=self.name)
        )

        if not result.succeeded():
            exceptions.append(Exception(f"Node '{self.name}': Failed to check connections for value_to_test"))
        elif not result.has_incoming_connections():
            exceptions.append(Exception(f"Node '{self.name}': value_to_test must have an incoming connection"))

        # Check 2: All cases have outgoing control connections - collect missing cases
        missing_case_names = []
        for index, case_param in enumerate(self.cases.get_child_parameters()):
            result = GriptapeNodes().handle_request(
                GetConnectionsForParameterRequest(parameter_name=case_param.name, node_name=self.name)
            )

            if not result.succeeded():
                case_name = self._get_case_display_name(case_param, index + 1)
                exceptions.append(Exception(f"Node '{self.name}': Failed to check connections for {case_name}"))
            elif not result.has_outgoing_connections():
                case_name = self._get_case_display_name(case_param, index + 1)
                missing_case_names.append(case_name)

        # If any cases are missing connections, create a single collated error message
        if missing_case_names:
            case_list = ", ".join(missing_case_names)
            exceptions.append(
                Exception(f"Cannot execute node '{self.name}'. Missing outgoing connections for {case_list}.")
            )

        # Call parent validation
        parent_exceptions = super().validate_before_workflow_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None

    def process(self) -> None:
        """Compare test value against cases and set control flow destination."""
        # Get the test value
        test_value = self.get_parameter_value("value_to_test")

        # Collect all case values and check for duplicates
        seen_values = set()
        duplicates = []
        case_value_to_param = {}

        for case_param in self.cases.get_child_parameters():
            case_value = self.get_parameter_value(case_param.name)

            if case_value in seen_values:
                duplicates.append(case_value)
            else:
                seen_values.add(case_value)
                case_value_to_param[case_value] = case_param

        # If duplicates found, report all of them
        if duplicates:
            duplicate_list = ", ".join(str(d) for d in duplicates)
            msg = f"Node '{self.name}': All case values must be unique. Duplicate values found: {duplicate_list}"
            raise ValueError(msg)

        # Find matching case
        if test_value in case_value_to_param:
            self.destination_control_flow = case_value_to_param[test_value]
            return

        # No match found - use "No Match" control output
        self.destination_control_flow = self.control_parameter_out

    def get_next_control_output(self) -> Parameter | None:
        """Return the control flow destination determined during process()."""
        return self.destination_control_flow
