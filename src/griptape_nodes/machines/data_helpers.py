from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.machines.execution_utils import Focus

from griptape_nodes.app.app import event_queue
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)

logger = logging.getLogger("griptape_nodes")


def pass_values_to_connected_nodes(current_focus: Focus) -> None:
    """Push parameter output values from the current node to all connected downstream nodes."""
    current_node = current_focus.node
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    for parameter_name, value in current_node.parameter_output_values.items():
        parameter = current_node.get_parameter_by_name(parameter_name)
        if parameter is None:
            message = (
                f"Canceling flow run. Node '{current_node.name}' specified a Parameter "
                f"'{parameter_name}', but no such Parameter could be found on that Node."
            )
            raise KeyError(message)
        data_type = parameter.type or ParameterTypeBuiltin.NONE.value
        event_queue.put(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=ParameterValueUpdateEvent(
                        node_name=current_node.name,
                        parameter_name=parameter_name,
                        data_type=data_type,
                        value=TypeValidator.safe_serialize(value),
                    )
                )
            )
        )
        # Pass the value through to the connected nodes.
        conn_output_nodes = GriptapeNodes.FlowManager().get_connected_output_parameters(current_node, parameter)
        for target_node, target_parameter in conn_output_nodes:
            GriptapeNodes.get_instance().handle_request(
                SetParameterValueRequest(
                    parameter_name=target_parameter.name,
                    node_name=target_node.name,
                    value=value,
                    data_type=parameter.output_type,
                )
            )


def get_library_name(node: BaseNode) -> str | None:
    """Return the registered library that owns *node* if exactly one match is found."""
    libraries = LibraryRegistry.get_libraries_with_node_type(node.__class__.__name__)
    return libraries[0] if len(libraries) == 1 else None


def clear_parameter_output_values(current_node: BaseNode) -> None:
    """Clear all parameter output values for *current_node* and notify the GUI."""
    for parameter_name in current_node.parameter_output_values.copy():
        parameter = current_node.get_parameter_by_name(parameter_name)
        if parameter is None:
            message = (
                f"Attempted to execute node '{current_node.name}' but could not find parameter "
                f"'{parameter_name}' that was indicated as having a value."
            )
            raise ValueError(message)
        parameter_type = parameter.type or ParameterTypeBuiltin.NONE.value
        payload = ParameterValueUpdateEvent(
            node_name=current_node.name,
            parameter_name=parameter_name,
            data_type=parameter_type,
            value=None,
        )
        event_queue.put(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
    current_node.parameter_output_values.clear()
