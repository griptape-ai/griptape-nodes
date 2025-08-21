from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.variable_types import VariableScope

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.traits.options import Options


class ScopeOption(StrEnum):
    NOT_SPECIFIED = "<not specified>"
    CURRENT_FLOW_ONLY = "current flow only"
    PARENT_FLOWS = "parent flows"
    GLOBAL_ONLY = "global only"
    ALL = "all flows"


class AdvancedParameterGroup(NamedTuple):
    parameter_group: ParameterGroup
    uuid_param: Parameter
    scope_param: Parameter


def create_advanced_parameter_group() -> AdvancedParameterGroup:
    """Create a collapsed Advanced parameter group with UUID and scope parameters.

    Returns:
        AdvancedParameterGroup with the parameter group and its child parameters
    """
    parameter_group = ParameterGroup(name="Advanced", ui_options={"collapsed": True})

    with parameter_group:
        uuid_param = Parameter(
            name="uuid",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="Optional UUID of the variable (takes precedence if provided)",
        )

        scope_param = Parameter(
            name="scope",
            type="str",
            default_value=ScopeOption.NOT_SPECIFIED.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            tooltip="Variable scope: hierarchical search, current flow only, or global only",
        )
        scope_param.add_trait(Options(choices=[option.value for option in ScopeOption]))

    return AdvancedParameterGroup(
        parameter_group=parameter_group,
        uuid_param=uuid_param,
        scope_param=scope_param,
    )


def scope_string_to_variable_scope(scope_str: str) -> "VariableScope":
    """Convert scope option string to VariableScope enum.

    Args:
        scope_str: The scope option string value

    Returns:
        VariableScope enum value, with PARENT_FLOWS as default for "not specified"
    """
    # Lazy import to avoid circular import issues
    from griptape_nodes.retained_mode.variable_types import VariableScope

    match scope_str:
        case ScopeOption.CURRENT_FLOW_ONLY.value:
            return VariableScope.CURRENT_FLOW_ONLY
        case ScopeOption.PARENT_FLOWS.value:
            return VariableScope.PARENT_FLOWS
        case ScopeOption.GLOBAL_ONLY.value:
            return VariableScope.GLOBAL_ONLY
        case ScopeOption.ALL.value:
            return VariableScope.ALL
        case ScopeOption.NOT_SPECIFIED.value:
            return VariableScope.PARENT_FLOWS
        case _:
            msg = f"Invalid scope option: {scope_str}"
            raise ValueError(msg)
