from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.variables.variable_utils import (
    create_advanced_parameter_group,
    scope_string_to_variable_scope,
)


class HasVariable(DataNode):
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
            tooltip="Name of the variable to check for existence",
        )
        self.add_parameter(self.variable_name_param)

        self.exists_param = Parameter(
            name="exists",
            type="bool",
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Whether the workflow variable exists",
        )
        self.add_parameter(self.exists_param)

        # Advanced parameters group (collapsed by default)
        advanced = create_advanced_parameter_group()
        self.uuid_param = advanced.uuid_param
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.variable_events import (
            HasVariableRequest,
            HasVariableResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        variable_name = self.get_parameter_value("variable_name")
        scope_str = self.get_parameter_value("scope")

        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        request = HasVariableRequest(
            name=variable_name,
            scope=scope,
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, HasVariableResultSuccess):
            self.parameter_output_values["exists"] = result.exists
            self.parameter_output_values["variable_name"] = variable_name
        else:
            msg = f"Failed to check variable existence: {result.result_details}"
            raise TypeError(msg)
