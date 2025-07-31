from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.app.app_sessions import event_queue
from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator

if TYPE_CHECKING:
    from griptape_nodes.machines.execution_utils import Focus
from griptape_nodes.machines.data_helpers import get_library_name
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
)

logger = logging.getLogger("griptape_nodes")


# Module-level helper functions for node execution utilities.


def mark_node_as_starting(current_focus: Focus) -> None:
    """Emit start events and flag the node as resolving."""
    current_node = current_focus.node
    current_node.state = NodeResolutionState.RESOLVING

    # Inform the GUI which node is now the active focus before we announce processing start.
    focus_payload = CurrentDataNodeEvent(node_name=current_node.name)
    event_queue.put(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=focus_payload)))
    event_queue.put(
        ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
        )
    )
    logger.info("Node '%s' is processing.", current_node.name)


def mark_node_as_finished(current_focus: Focus) -> None:
    """Emit finished events and flag the node as resolved."""
    current_node = current_focus.node
    logger.info("Node '%s' finished processing.", current_node.name)

    event_queue.put(
        ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
        )
    )
    lib_name = get_library_name(current_node)
    event_queue.put(
        ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=NodeResolvedEvent(
                    node_name=current_node.name,
                    parameter_output_values=TypeValidator.safe_serialize(current_node.parameter_output_values),
                    node_type=current_node.__class__.__name__,
                    specific_library_name=lib_name,
                )
            )
        )
    )
    current_node.state = NodeResolutionState.RESOLVED
    logger.info("'%s' resolved.", current_node.name)


def log_serialization(current_focus: Focus) -> None:
    """Serialize node inputs/outputs for debug logging when log-level is DEBUG."""
    current_node = current_focus.node
    if logger.level <= logging.DEBUG:
        logger.debug(
            "INPUTS: %s\nOUTPUTS: %s",
            TypeValidator.safe_serialize(current_node.parameter_values),
            TypeValidator.safe_serialize(current_node.parameter_output_values),
        )
