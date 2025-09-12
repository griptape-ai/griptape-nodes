from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options


def update_option_choices(node: BaseNode, parameter_name: str, choices: list[str], default: str) -> None:
    """Updates the model selection parameter with a new set of choices.

    This function is intended to be called by subclasses to set the available
    models for the driver. It modifies the 'model' parameter's `Options` trait
    to reflect the provided choices.

    Args:
        node: The node containing the parameter to update.
        parameter_name: The name of the parameter representing the model selection.
        choices: A list of model names to be set as choices.
        default: The default model name to be set. It must be one of the provided choices.
    """
    parameter = node.get_parameter_by_name(parameter_name)
    if parameter is not None:
        # Find the Options trait by type since element_id is a UUID
        traits = parameter.find_elements_by_type(Options)
        if traits:
            trait = traits[0]  # Take the first Options trait
            trait.choices = choices

            if default in choices:
                parameter.default_value = default
                node.set_parameter_value(parameter_name, default)
            else:
                msg = f"Default model '{default}' is not in the provided choices."
                raise ValueError(msg)

            # Update the manually set UI options to include the new simple_dropdown
            if hasattr(parameter, "_ui_options") and parameter._ui_options:
                parameter._ui_options["simple_dropdown"] = choices

                # Force the parameter to emit an update event to refresh UI options
                parameter._emit_alter_element_event_if_possible()
        else:
            msg = f"No Options trait found for parameter '{parameter_name}'."
            raise ValueError(msg)
    else:
        msg = f"Parameter '{parameter_name}' not found for updating model choices."
        raise ValueError(msg)


def remove_options_trait(node: BaseNode, parameter_name: str) -> None:
    """Removes the Options trait from the specified parameter.

    Args:
        node: The node containing the parameter to update.
        parameter_name: The name of the parameter to remove the Options trait from.
    """
    parameter = node.get_parameter_by_name(parameter_name)
    if parameter is not None:
        # Find the Options trait by type since element_id is a UUID
        traits = parameter.find_elements_by_type(Options)
        if traits:
            trait = traits[0]  # Take the first Options trait
            parameter.remove_trait(trait)
        else:
            msg = f"No Options trait found for parameter '{parameter_name}'."
            raise ValueError(msg)
    else:
        msg = f"Parameter '{parameter_name}' not found for removing options trait."
        raise ValueError(msg)
