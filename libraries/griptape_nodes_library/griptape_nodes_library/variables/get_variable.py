from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes_library.variables.variable_utils import (
    create_advanced_parameter_group,
    scope_string_to_variable_scope,
)


class GetVariable(ControlNode):
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
        self.scope_param = advanced.scope_param
        self.add_node_element(advanced.parameter_group)

    def process(self) -> None:
        # Lazy imports to avoid circular import issues
        from griptape_nodes.retained_mode.events.node_events import (
            GetFlowForNodeRequest,
            GetFlowForNodeResultSuccess,
        )
        from griptape_nodes.retained_mode.events.variable_events import (
            GetVariableValueRequest,
            GetVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        variable_name = self.get_parameter_value("variable_name")
        scope_str = self.get_parameter_value("scope")

        # Convert scope string to VariableScope enum
        scope = scope_string_to_variable_scope(scope_str)

        # Get the flow that owns this node
        flow_request = GetFlowForNodeRequest(node_name=self.name)
        flow_result = GriptapeNodes.handle_request(flow_request)

        if not isinstance(flow_result, GetFlowForNodeResultSuccess):
            error_msg = f"Failed to get flow for node '{self.name}': {flow_result.result_details}"
            raise TypeError(error_msg)

        current_flow_name = flow_result.flow_name

        request = GetVariableValueRequest(
            name=variable_name,
            lookup_scope=scope,
            starting_flow=current_flow_name,
        )

        result = GriptapeNodes.handle_request(request)

        if isinstance(result, GetVariableValueResultSuccess):
            self.parameter_output_values["value"] = deepcopy(result.value)
            self.parameter_output_values["variable_name"] = variable_name
        else:
            msg = f"Failed to get variable: {result.result_details}"
            raise TypeError(msg)

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
