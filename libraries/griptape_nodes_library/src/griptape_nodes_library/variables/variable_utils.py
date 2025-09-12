from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.variable_types import VariableScope

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
