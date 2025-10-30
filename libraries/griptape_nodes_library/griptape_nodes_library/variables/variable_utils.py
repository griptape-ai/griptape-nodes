from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.variable_types import FlowVariable, VariableScope

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.traits.options import Options


class AdvancedParameterGroup(NamedTuple):
    parameter_group: ParameterGroup
    scope_param: Parameter


def create_advanced_parameter_group() -> AdvancedParameterGroup:
    """Create a collapsed Advanced parameter group with scope parameter.

    Returns:
        AdvancedParameterGroup with the parameter group and its child parameters
    """
    # Lazy import to avoid circular import issues
    from griptape_nodes.retained_mode.variable_types import VariableScope

    parameter_group = ParameterGroup(name="Advanced", ui_options={"collapsed": True})

    # Create user-friendly display labels for the scope options
    scope_choices = [
        VariableScope.HIERARCHICAL.value,
        VariableScope.CURRENT_FLOW_ONLY.value,
        VariableScope.GLOBAL_ONLY.value,
        VariableScope.ALL.value,
    ]

    with parameter_group:
        scope_param = Parameter(
            name="scope",
            type="str",
            default_value=VariableScope.HIERARCHICAL.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="Variable scope: hierarchical search, current flow only, global only, or all flows",
        )
        scope_param.add_trait(Options(choices=scope_choices))

    return AdvancedParameterGroup(
        parameter_group=parameter_group,
        scope_param=scope_param,
    )


def scope_string_to_variable_scope(scope_str: str) -> "VariableScope":
    """Convert scope string to VariableScope enum.

    Args:
        scope_str: The scope string value

    Returns:
        VariableScope enum value
    """
    # Lazy import to avoid circular import issues
    from griptape_nodes.retained_mode.variable_types import VariableScope

    # Direct mapping since we're using VariableScope values directly
    try:
        return VariableScope(scope_str)
    except ValueError:
        msg = f"Invalid scope option: {scope_str}"
        raise ValueError(msg) from None


def get_variable(node_name: str, variable_name: str, scope: "VariableScope") -> "FlowVariable":
    """Attempts to get a variable at the specified scope.

    Args:
        node_name: The name of the node requesting the variable
        variable_name: The name of the variable to retrieve
        scope: The scope to search for the variable within

    Returns:
        The FlowVariable object (which has variable name, type, value, etc.)

    Raises:
        RuntimeError: If the flow for the node cannot be found
        LookupError: If the variable cannot be retrieved
    """
    # Lazy imports to avoid circular import issues
    from griptape_nodes.retained_mode.events.variable_events import (
        GetVariableRequest,
        GetVariableResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    current_flow_name = _get_flow_for_node(node_name)

    request = GetVariableRequest(
        name=variable_name,
        lookup_scope=scope,
        starting_flow=current_flow_name,
    )

    result = GriptapeNodes.handle_request(request)
    if not isinstance(result, GetVariableResultSuccess):
        msg = f"Failed to get variable: {result.result_details}"
        raise LookupError(msg)  # noqa: TRY004
    return result.variable


def has_variable(node_name: str, variable_name: str, scope: "VariableScope") -> bool:
    """Attempts to check if a variable exists at the specified scope.

    Args:
        node_name: The name of the node requesting the variable check
        variable_name: The name of the variable to check
        scope: The scope to search for the variable within

    Returns:
        True if the variable exists, False otherwise

    Raises:
        RuntimeError: If the flow for the node cannot be found
    """
    # Lazy imports to avoid circular import issues
    from griptape_nodes.retained_mode.events.variable_events import (
        HasVariableRequest,
        HasVariableResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    current_flow_name = _get_flow_for_node(node_name)

    request = HasVariableRequest(
        name=variable_name,
        lookup_scope=scope,
        starting_flow=current_flow_name,
    )

    result = GriptapeNodes.handle_request(request)
    if not isinstance(result, HasVariableResultSuccess):
        msg = f"Failed to check variable: {result.result_details}"
        raise RuntimeError(msg)  # noqa: TRY004
    return result.exists


def _get_flow_for_node(node_name: str) -> str:
    """Get the flow name that owns a given node.

    Args:
        node_name: The name of the node to look up

    Returns:
        The name of the flow that owns the node

    Raises:
        RuntimeError: If the flow for the node cannot be found
    """
    # Lazy imports to avoid circular import issues
    from griptape_nodes.retained_mode.events.node_events import (
        GetFlowForNodeRequest,
        GetFlowForNodeResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    flow_request = GetFlowForNodeRequest(node_name=node_name)
    flow_result = GriptapeNodes.handle_request(flow_request)

    if not isinstance(flow_result, GetFlowForNodeResultSuccess):
        error_msg = f"Failed to get flow for node '{node_name}': {flow_result.result_details}"
        raise RuntimeError(error_msg)  # noqa: TRY004

    return flow_result.flow_name
