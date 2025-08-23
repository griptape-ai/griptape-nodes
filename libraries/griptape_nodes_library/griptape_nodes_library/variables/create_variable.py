import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode

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
            type=ParameterTypeBuiltin.STR.value,
            default_value=None,
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="The user-defined type of the variable (e.g., 'JSON', 'str', 'int')",
        )
        self.add_parameter(self.variable_type_param)

        self.value_param = Parameter(
            name="value",
            type=ParameterTypeBuiltin.ANY.value,
            input_types=[ParameterTypeBuiltin.ANY.value],
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="The initial value of the variable",
        )
        self.add_parameter(self.value_param)

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle incoming connections, especially to the value parameter for auto-type detection."""
        if target_parameter.name == self.value_param.name:
            detected_type = source_parameter.output_type

            # Lock down the variable_type parameter since it's now controlled by the incoming connection
            # Remove INPUT mode so users can't manually edit it while a connection exists
            self.variable_type_param.allowed_modes = self.variable_type_param.allowed_modes - {ParameterMode.INPUT}
            # Make it non-settable programmatically to prevent external interference
            self.variable_type_param.settable = False

            # Clean up any existing incoming connections to variable_type since we're now the authority
            # This prevents conflicts between manual type setting and auto-detected type
            self._delete_incoming_connections_to_parameter(self.variable_type_param.name)

            # Set the detected type as the new value
            # Note: this call will trigger the before_value_set callback,
            # which will setup the value_param's types properly.
            self.set_parameter_value(self.variable_type_param.name, detected_type)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Handle removal of incoming connections, especially from the value parameter."""
        if target_parameter.name == self.value_param.name:
            # Restore INPUT mode to variable_type parameter since auto-detection is no longer active
            self.variable_type_param.allowed_modes = self.variable_type_param.allowed_modes | {ParameterMode.INPUT}
            # Make it settable again for manual editing
            self.variable_type_param.settable = True

    def _delete_incoming_connections_to_parameter(self, parameter_name: str) -> None:
        """Helper to delete all incoming connections to a specific parameter."""
        from griptape_nodes.retained_mode.events.connection_events import (
            DeleteConnectionRequest,
            DeleteConnectionResultSuccess,
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections_request = ListConnectionsForNodeRequest(node_name=self.name)
        connections_result = GriptapeNodes.handle_request(connections_request)

        if not isinstance(connections_result, ListConnectionsForNodeResultSuccess):
            error_msg = f"Failed to list connections for node '{self.name}': {connections_result.result_details}"
            raise TypeError(error_msg)

        for connection in connections_result.incoming_connections:
            if connection.target_parameter_name == parameter_name:
                delete_request = DeleteConnectionRequest(
                    source_parameter_name=connection.source_parameter_name,
                    target_parameter_name=connection.target_parameter_name,
                    source_node_name=connection.source_node_name,
                    target_node_name=self.name,
                )
                delete_result = GriptapeNodes.handle_request(delete_request)
                if not isinstance(delete_result, DeleteConnectionResultSuccess):
                    error_msg = f"Failed to delete connection from {connection.source_node_name}.{connection.source_parameter_name} to {self.name}.{parameter_name}: {delete_result.result_details}"
                    raise TypeError(error_msg)

    def _cleanup_incompatible_value_connections(self) -> None:
        """Remove all connections to/from value parameter that are incompatible with its current type."""
        from griptape_nodes.retained_mode.events.connection_events import (
            DeleteConnectionRequest,
            DeleteConnectionResultSuccess,
            ListConnectionsForNodeRequest,
            ListConnectionsForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections_request = ListConnectionsForNodeRequest(node_name=self.name)
        connections_result = GriptapeNodes.handle_request(connections_request)

        if isinstance(connections_result, ListConnectionsForNodeResultSuccess):
            # Check incoming connections - we are the target
            for connection in connections_result.incoming_connections:
                if connection.target_parameter_name == self.value_param.name:
                    source_node = GriptapeNodes.NodeManager().get_node_by_name(connection.source_node_name)
                    source_parameter = source_node.get_parameter_by_name(connection.source_parameter_name)

                    # Ask if we (target) accept the source parameter's output_type
                    if source_parameter and not self.value_param.is_incoming_type_allowed(source_parameter.output_type):
                        logger.debug(
                            "Deleting incompatible incoming connection: %s.%s (%s) -> %s.%s (%s)",
                            connection.source_node_name,
                            connection.source_parameter_name,
                            source_parameter.output_type,
                            self.name,
                            connection.target_parameter_name,
                            self.value_param.type,
                        )
                        delete_request = DeleteConnectionRequest(
                            source_node_name=connection.source_node_name,
                            source_parameter_name=connection.source_parameter_name,
                            target_node_name=self.name,
                            target_parameter_name=connection.target_parameter_name,
                        )
                        delete_result = GriptapeNodes.handle_request(delete_request)
                        if not isinstance(delete_result, DeleteConnectionResultSuccess):
                            error_msg = (
                                f"Failed to delete incompatible incoming connection: {delete_result.result_details}"
                            )
                            raise TypeError(error_msg)

            # Check outgoing connections - we are the source
            for connection in connections_result.outgoing_connections:
                if connection.source_parameter_name == self.value_param.name:
                    target_node = GriptapeNodes.NodeManager().get_node_by_name(connection.target_node_name)
                    target_parameter = target_node.get_parameter_by_name(connection.target_parameter_name)

                    # Ask if the target accepts our output_type
                    if target_parameter and not target_parameter.is_incoming_type_allowed(self.value_param.output_type):
                        logger.debug(
                            "Deleting incompatible outgoing connection: %s.%s (%s) -> %s.%s (%s)",
                            self.name,
                            connection.source_parameter_name,
                            self.value_param.output_type,
                            connection.target_node_name,
                            connection.target_parameter_name,
                            target_parameter.type,
                        )
                        delete_request = DeleteConnectionRequest(
                            source_node_name=self.name,
                            source_parameter_name=connection.source_parameter_name,
                            target_node_name=connection.target_node_name,
                            target_parameter_name=connection.target_parameter_name,
                        )
                        delete_result = GriptapeNodes.handle_request(delete_request)
                        if not isinstance(delete_result, DeleteConnectionResultSuccess):
                            error_msg = (
                                f"Failed to delete incompatible outgoing connection: {delete_result.result_details}"
                            )
                            raise TypeError(error_msg)

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        """Handle changes to the variable_type parameter."""
        if parameter == self.variable_type_param:
            # Step 1: If variable_type_param is set to None or "", assign it to None
            if value is None or value == "":
                value = None

            # Step 2: If variable_type_param is being set to None, reset value_param to defaults
            if value is None:
                # Leave all outgoing connections from value_param intact
                # Change value_param's type to ANY and output_type to ALL
                self.value_param.type = ParameterTypeBuiltin.ANY.value
                self.value_param.output_type = ParameterTypeBuiltin.ALL.value
            else:
                # Step 3: If variable_type_param is NOT being set to None, delete incompatible connections
                # Update value_param type information first
                self.value_param.type = value
                self.value_param.output_type = value

                # Clean up incompatible connections
                self._cleanup_incompatible_value_connections()

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
