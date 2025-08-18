from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.variables.variable_utils import create_advanced_parameter_group, scope_string_to_variable_scope


class GetWorkflowVariable(DataNode):
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
            tooltip="Name of the variable to retrieve",
        )
        self.add_parameter(self.variable_name_param)

        self.value_param = Parameter(
            name="value",
            type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="The value of the workflow variable",
        )
        self.add_parameter(self.value_param)

        # Advanced parameters group (collapsed by default)
        advanced = create_advanced_parameter_group()
        self.uuid_param = advanced.uuid_param
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.workflow_variable_events import (
            GetWorkflowVariableValueRequest,
            GetWorkflowVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        
        uuid = self.get_parameter_value("uuid")
        variable_name = self.get_parameter_value("variable_name")
        scope_str = self.get_parameter_value("scope")
        
        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        request = GetWorkflowVariableValueRequest(
            uuid=uuid if uuid else None,
            name=variable_name if variable_name else None,
            scope=scope,
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, GetWorkflowVariableValueResultSuccess):
            self.parameter_output_values["value"] = deepcopy(result.value)
            self.parameter_output_values["variable_name"] = variable_name
        else:
            raise RuntimeError(f"Failed to get workflow variable: {result.result_details}")