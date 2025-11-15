from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import ControlNode, NodeResolutionState
from griptape_nodes_library.variables.variable_utils import (
    create_advanced_parameter_group,
    get_variable,
    scope_string_to_variable_scope,
)


class SetVariable(ControlNode):
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
            type=ParameterTypeBuiltin.ANY.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="The new value to set for the workflow variable",
        )
        self.add_parameter(self.value_param)

        # Advanced parameters group (collapsed by default)
        advanced = create_advanced_parameter_group()
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.variable_events import (
            SetVariableValueRequest,
            SetVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        variable_name = self.get_parameter_value(self.variable_name_param.name)
        value = self.get_parameter_value(self.value_param.name)
        scope_str = self.get_parameter_value(self.scope_param.name)

        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        # Verify the variable exists using the get_variable helper
        # This will raise RuntimeError or LookupError if there are issues
        var_info = get_variable(node_name=self.name, variable_name=variable_name, scope=scope)

        request = SetVariableValueRequest(
            value=value,
            name=variable_name,
            lookup_scope=scope,
            starting_flow=var_info.owning_flow_name,  # Re-assign at the level the variable is at.
        )

        result = GriptapeNodes.handle_request(request)

        if not isinstance(result, SetVariableValueResultSuccess):
            msg = f"Failed to set variable: {result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Set output values.
        self.parameter_output_values[self.variable_name_param.name] = variable_name

    @property
    def state(self) -> NodeResolutionState:
        """Overrides BaseNode.state @property to treat it as volatile (if the value has changed, mark as unresolved)."""
        if self._state == NodeResolutionState.RESOLVED:
            variable_name = self.get_parameter_value(self.variable_name_param.name)
            scope_str = self.get_parameter_value(self.scope_param.name)

            # Convert scope string to VariableScope enum
            scope = scope_string_to_variable_scope(scope_str)

            # This can throw if the variable doesn't exist.
            try:
                variable = get_variable(node_name=self.name, variable_name=variable_name, scope=scope)

                var_value = variable.value
                our_value = self.get_parameter_value(self.value_param.name)
                if var_value != our_value:
                    return NodeResolutionState.UNRESOLVED
            except LookupError:
                # Variable may not have been created yet; assume unresolved.
                return NodeResolutionState.UNRESOLVED
        return super().state

    @state.setter
    def state(self, new_state: NodeResolutionState) -> None:
        # Have to override the setter if we override the getter.
        self._state = new_state
