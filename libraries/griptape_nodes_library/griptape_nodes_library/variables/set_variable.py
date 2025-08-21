from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.variables.variable_utils import (
    create_advanced_parameter_group,
    scope_string_to_variable_scope,
)


class SetVariable(DataNode):
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
            tooltip="Name of the variable to set",
        )
        self.add_parameter(self.variable_name_param)

        self.value_param = Parameter(
            name="value",
            type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="The new value to set for the workflow variable",
        )
        self.add_parameter(self.value_param)

        # Advanced parameters group (collapsed by default)
        advanced = create_advanced_parameter_group()
        self.uuid_param = advanced.uuid_param
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.variable_events import (
            SetVariableValueRequest,
            SetVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        variable_name = self.get_parameter_value("variable_name")
        value = self.get_parameter_value("value")
        scope_str = self.get_parameter_value("scope")

        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        request = SetVariableValueRequest(
            value=value,
            name=variable_name,
            scope=scope,
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, SetVariableValueResultSuccess):
            self.parameter_output_values["variable_name"] = variable_name
        else:
            msg = f"Failed to set variable: {result.result_details}"
            raise TypeError(msg)
