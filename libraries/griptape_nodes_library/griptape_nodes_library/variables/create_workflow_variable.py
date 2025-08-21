import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

logger = logging.getLogger("griptape_nodes")


class CreateVariable(DataNode):
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

        self.is_global_param = Parameter(
            name="is_global",
            type="bool",
            default_value=False,
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            tooltip="Whether this is a global variable (true) or current flow variable (false)",
        )
        self.add_parameter(self.is_global_param)

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
        from griptape_nodes.retained_mode.events.workflow_variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        from griptape_nodes.retained_mode.workflow_variable_types import VariableScope

        variable_name = self.get_parameter_value("variable_name")
        is_global = self.get_parameter_value("is_global")
        scope = VariableScope.GLOBAL if is_global else VariableScope.CURRENT_FLOW
        variable_type = self.get_parameter_value("variable_type")
        value = self.get_parameter_value("value")

        request = CreateVariableRequest(
            name=variable_name,
            scope=scope,
            type=variable_type,
            value=value,
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, CreateVariableResultSuccess):
            # Set output values
            self.parameter_output_values["variable_name"] = variable_name
            self.parameter_output_values["is_global"] = is_global
            self.parameter_output_values["variable_type"] = variable_type
            self.parameter_output_values["value"] = value
        else:
            error_msg = f"Failed to create variable: {result.result_details}"
            raise TypeError(error_msg)
