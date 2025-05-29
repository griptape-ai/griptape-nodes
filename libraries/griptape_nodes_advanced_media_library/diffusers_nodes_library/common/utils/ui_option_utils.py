from griptape_nodes.exe_types.node_types import BaseNode


def update_ui_option_hide(node: BaseNode, parameter_name: str, *, hide: bool) -> None:
    """Updates the ui_option hide for a parameter.

    Args:
        node: The node containing the parameter to be updated.
        parameter_name: The name of the parameter whose UI options are to be modified.
        hide: A boolean indicating whether to hide the parameter in the UI.
    """
    parameter = node.get_parameter_by_name(parameter_name)
    if parameter is not None:
        parameter._ui_options["hide"] = hide
    else:
        msg = f"Parameter '{parameter_name}' not found for updating ui_option hide."
        raise ValueError(msg)
