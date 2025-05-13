from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options


def update_option_choices(node: BaseNode, parameter_name: str, choices: list[str], default: str) -> None:
    """Updates the model selection parameter with a new set of choices.

    Args:
        node: The node containing the parameter to be updated.
        parameter_name: The name of the parameter representing the model selection or the Parameter object itself.
        choices: A list of model names to be set as choices.
        default: The default model name to be set. It must be one of the provided choices.
    """
    parameter = node.get_parameter_by_name(parameter_name)
    if parameter is not None:
        trait = parameter.find_element_by_id("Options")
        if trait and isinstance(trait, Options):
            trait.choices = choices

            if default in choices:
                parameter.default_value = default
                node.set_parameter_value(parameter_name, default)
            else:
                msg = f"Default model '{default}' is not in the provided choices."
                raise ValueError(msg)
    else:
        msg = f"Parameter '{parameter_name}' not found for updating model choices."
        raise ValueError(msg)


def remove_options_trait(node: BaseNode, parameter_name: str) -> None:
    """Removes the options trait from the specified parameter.

    Args:
        node: The node from which to remove the options trait.
        parameter_name: The name of the parameter from which to remove the `Options` trait.
    """
    parameter = node.get_parameter_by_name(parameter_name)
    if parameter is not None:
        trait = parameter.find_element_by_id("Options")
        if trait and isinstance(trait, Options):
            parameter.remove_trait(trait)
    else:
        msg = f"Parameter '{parameter_name}' not found for removing options trait."
        raise ValueError(msg)
