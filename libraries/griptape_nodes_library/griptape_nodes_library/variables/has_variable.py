from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode, NodeResolutionState
from griptape_nodes_library.variables.variable_utils import (
    create_advanced_parameter_group,
    has_variable,
    scope_string_to_variable_scope,
)


class HasVariable(ControlNode):
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
            default_value=False,
            allowed_modes={ParameterMode.OUTPUT},
            tooltip="Whether the workflow variable exists",
        )
        self.add_parameter(self.exists_param)

        # Advanced parameters group (collapsed by default)
        advanced = create_advanced_parameter_group()
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        variable_name = self.get_parameter_value(self.variable_name_param.name)
        scope_str = self.get_parameter_value(self.scope_param.name)

        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        # This can throw.
        exists = has_variable(node_name=self.name, variable_name=variable_name, scope=scope)

        self.set_parameter_value(self.exists_param.name, exists)

        # Set output values.
        self.parameter_output_values[self.exists_param.name] = exists
        self.parameter_output_values[self.variable_name_param.name] = variable_name

    @property
    def state(self) -> NodeResolutionState:
        """Overrides BaseNode.state @property to treat it as volatile (always be re-evaluated every time it is executed)."""
        if self._state == NodeResolutionState.RESOLVED:
            variable_name = self.get_parameter_value(self.variable_name_param.name)
            scope_str = self.get_parameter_value(self.scope_param.name)

            # Convert scope string to VariableScope enum
            scope = scope_string_to_variable_scope(scope_str)

            # This can throw.
            try:
                var_exists = has_variable(node_name=self.name, variable_name=variable_name, scope=scope)
                our_exists = self.get_parameter_value(self.exists_param.name)
                if var_exists != our_exists:
                    # We're dirty.
                    return NodeResolutionState.UNRESOLVED
            except RuntimeError:
                # Variable may not be created yet; assume unresolved.
                return NodeResolutionState.UNRESOLVED
        return super().state

    @state.setter
    def state(self, new_state: NodeResolutionState) -> None:
        # Have to override the setter if we override the getter.
        self._state = new_state
