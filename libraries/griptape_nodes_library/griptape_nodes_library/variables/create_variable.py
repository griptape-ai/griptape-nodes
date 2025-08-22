import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

logger = logging.getLogger("griptape_nodes")


class CreateVariable(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.variable_name_param = Parameter(
            name="variable_name",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="The name of the variable to create",
        )
        self.add_parameter(self.variable_name_param)

        self.variable_type_param = Parameter(
            name="variable_type",
            type="str",
            default_value="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="The user-defined type of the variable (e.g., 'JSON', 'str', 'int')",
        )
        self.add_parameter(self.variable_type_param)

        self.value_param = Parameter(
            name="value",
            type="str",
            input_types=["str"],
            output_type="str",
            default_value=None,
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="The initial value of the variable",
        )
        self.add_parameter(self.value_param)

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        """Handle dynamic type changes for the value parameter.

        When the variable_type parameter changes, we need to:
        1. Update the value parameter's type information to match the new variable type
        2. Delete any existing connections to/from the value parameter since the type changed
        3. Log a warning to inform the user that connections were broken due to type change

        This ensures type safety and prevents invalid connections from persisting.
        """
        if parameter == self.variable_type_param and value != parameter.default_value:
            current_type = self.parameter_values.get("variable_type", "str")
            if value != current_type:
                # Lazy imports to avoid circular import issues
                from griptape_nodes.retained_mode.events.connection_events import (
                    DeleteConnectionRequest,
                    ListConnectionsForNodeRequest,
                    ListConnectionsForNodeResultSuccess,
                )
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                # Get all connections for this node to find connections to/from the value parameter
                connections_request = ListConnectionsForNodeRequest(node_name=self.name)
                connections_result = GriptapeNodes.handle_request(connections_request)

                connections_deleted = False

                # Delete outgoing connections from the value parameter
                # These are connections where our value parameter is the source
                if isinstance(connections_result, ListConnectionsForNodeResultSuccess):
                    for connection in connections_result.outgoing_connections:
                        if connection.source_parameter_name == "value":
                            delete_request = DeleteConnectionRequest(
                                source_parameter_name=connection.source_parameter_name,
                                target_parameter_name=connection.target_parameter_name,
                                source_node_name=self.name,
                                target_node_name=connection.target_node_name,
                            )
                            GriptapeNodes.handle_request(delete_request)
                            connections_deleted = True

                    # Delete incoming connections to the value parameter
                    # These are connections where our value parameter is the target
                    for connection in connections_result.incoming_connections:
                        if connection.target_parameter_name == "value":
                            delete_request = DeleteConnectionRequest(
                                source_parameter_name=connection.source_parameter_name,
                                target_parameter_name=connection.target_parameter_name,
                                source_node_name=connection.source_node_name,
                                target_node_name=self.name,
                            )
                            GriptapeNodes.handle_request(delete_request)
                            connections_deleted = True

                    if connections_deleted:
                        warning_msg = f"Variable type changed from '{current_type}' to '{value}', deleted connections from value parameter"
                        logger.warning(warning_msg)

                # Update the value parameter's type information to match the new variable type
                # This ensures type compatibility for future connections
                self.value_param.input_types = [value]
                self.value_param.output_type = value
                self.value_param.type = value

        return value

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.node_events import (
            GetFlowForNodeRequest,
            GetFlowForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
            GetVariableDetailsRequest,
            GetVariableDetailsResultSuccess,
            HasVariableRequest,
            HasVariableResultSuccess,
            SetVariableTypeRequest,
            SetVariableTypeResultSuccess,
            SetVariableValueRequest,
            SetVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.variable_types import VariableScope

        variable_name = self.get_parameter_value("variable_name")
        variable_type = self.get_parameter_value("variable_type")
        value = self.get_parameter_value("value")

        # Get the flow that owns this node
        flow_request = GetFlowForNodeRequest(node_name=self.name)
        flow_result = GriptapeNodes.handle_request(flow_request)

        if not isinstance(flow_result, GetFlowForNodeResultSuccess):
            error_msg = f"Failed to get flow for node '{self.name}': {flow_result.result_details}"
            raise TypeError(error_msg)

        current_flow_name = flow_result.flow_name

        # Step 1: Check if the variable already exists in the current flow
        has_request = HasVariableRequest(
            name=variable_name,
            lookup_scope=VariableScope.CURRENT_FLOW_ONLY,
            starting_flow=current_flow_name,
        )
        has_result = GriptapeNodes.handle_request(has_request)

        if not isinstance(has_result, HasVariableResultSuccess):
            error_msg = f"Failed to check if variable '{variable_name}' exists: {has_result.result_details}"
            raise TypeError(error_msg)

        if has_result.exists:
            # Variable exists - check if type needs updating
            # Step 2a: Get variable details to check type
            details_request = GetVariableDetailsRequest(
                name=variable_name,
                lookup_scope=VariableScope.CURRENT_FLOW_ONLY,
                starting_flow=current_flow_name,
            )
            details_result = GriptapeNodes.handle_request(details_request)

            if not isinstance(details_result, GetVariableDetailsResultSuccess):
                error_msg = (
                    f"Failed to get details for existing variable '{variable_name}': {details_result.result_details}"
                )
                raise TypeError(error_msg)

            # Step 2b: Update type if it doesn't match
            if details_result.details.type != variable_type:
                type_request = SetVariableTypeRequest(
                    name=variable_name,
                    type=variable_type,
                    lookup_scope=VariableScope.CURRENT_FLOW_ONLY,
                    starting_flow=current_flow_name,
                )
                type_result = GriptapeNodes.handle_request(type_request)

                if not isinstance(type_result, SetVariableTypeResultSuccess):
                    error_msg = f"Failed to update type for variable '{variable_name}': {type_result.result_details}"
                    raise TypeError(error_msg)

            # Step 3: Update the value for existing variable
            value_request = SetVariableValueRequest(
                name=variable_name,
                value=value,
                lookup_scope=VariableScope.CURRENT_FLOW_ONLY,
                starting_flow=current_flow_name,
            )
            value_result = GriptapeNodes.handle_request(value_request)

            if not isinstance(value_result, SetVariableValueResultSuccess):
                error_msg = f"Failed to set value for variable '{variable_name}': {value_result.result_details}"
                raise TypeError(error_msg)
        else:
            # Variable doesn't exist - create it (creation includes setting the initial value)
            create_request = CreateVariableRequest(
                name=variable_name,
                type=variable_type,
                is_global=False,  # Always create flow-scoped variables
                value=value,
                owning_flow=current_flow_name,
            )
            create_result = GriptapeNodes.handle_request(create_request)

            if not isinstance(create_result, CreateVariableResultSuccess):
                error_msg = f"Failed to create variable '{variable_name}': {create_result.result_details}"
                raise TypeError(error_msg)

        # Set output values
        self.parameter_output_values["variable_name"] = variable_name
        self.parameter_output_values["variable_type"] = variable_type
        self.parameter_output_values["value"] = value

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Variable nodes have side effects and need to execute every workflow run."""
        from griptape_nodes.exe_types.node_types import NodeResolutionState
        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )
        return None

    def validate_before_node_run(self) -> list[Exception] | None:
        """Variable nodes have side effects and need to execute every time they run."""
        from griptape_nodes.exe_types.node_types import NodeResolutionState
        self.make_node_unresolved(
            current_states_to_trigger_change_event={NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
        )
        return None
