from __future__ import annotations

from collections import defaultdict
from typing import Any

from griptape_nodes.exe_types.node_types import BaseNode
from typing import Generator

from dataclasses import dataclass
from griptape_nodes.machines.fsm import State

import logging
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from griptape.events import EventBus
from griptape.utils import with_contextvars

from griptape_nodes.app.app_sessions import event_queue
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    NodeFinishProcessEvent,
    NodeStartProcessEvent,
    ParameterValueUpdateEvent,
    CurrentDataNodeEvent
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)

logger = logging.getLogger("griptape_nodes")

# Directed Acyclic Graph
class DAG:
    """Directed Acyclic Graph for tracking node dependencies during resolution."""
    def __init__(self):
        """Initialize the DAG with empty graph and in-degree structures."""
        self.graph = defaultdict(set)        # adjacency list
        self.in_degree = defaultdict(int)    # number of unmet dependencies

    def add_node(self, node: BaseNode) -> None:
        """Ensure the node exists in the graph."""
        self.graph[node]

    def add_edge(self, from_node: BaseNode, to_node: BaseNode) -> None:
        """Add a directed edge from 'from_node' to 'to_node'."""
        self.graph[from_node].add(to_node)
        self.in_degree[to_node] += 1

    def get_ready_nodes(self) -> list[BaseNode]:
        """Return nodes with no unmet dependencies (in-degree 0)."""
        return [node for node in self.graph if self.in_degree[node] == 0]

    def mark_processed(self, node: BaseNode) -> None:
        """Mark a node as processed, decrementing in-degree of its dependents."""
        # Remove outgoing edges from this node
        for dependent in self.graph[node]:
            self.in_degree[dependent] -= 1
        self.graph.pop(node, None)
        self.in_degree.pop(node, None)

    def get_all_nodes(self) -> list[BaseNode]:
        """Return a list of all nodes currently in the DAG."""
        return list(self.graph.keys())


@dataclass
class Focus:
    """Represents a node currently being resolved, with optional scheduled value and generator."""
    node: BaseNode
    scheduled_value: Any | None = None
    updated: bool = True
    process_generator: Generator | None = None


# This is on a per-node basis
class ResolutionContext:
    """Context for node resolution, including the focus stack, DAG, and paused state."""
    root_node_resolving: BaseNode | None
    current_focuses: list[Focus]
    paused: bool
    DAG: DAG

    def __init__(self) -> None:
        """Initialize the resolution context with empty DAG."""
        self.paused = False
        self.DAG = DAG()
        self.current_focuses = []
        self.root_node_resolving = None

    def reset(self) -> None:
        """Reset the DAG, and paused state."""
        if self.DAG is not None:
            for node in self.DAG.graph:
                node.clear_node()
            self.DAG.graph.clear()
            self.DAG.in_degree.clear()
        self.paused = False


class CompleteState(State):
    """State indicating node resolution is complete."""
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        """Enter the CompleteState."""
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        """Update the CompleteState (no-op)."""
        return None

class ExecuteNodeHelpers:
    """Collection of static helper utilities used while a node is executing."""
    @staticmethod
    def _mark_node_as_starting(context: ResolutionContext, current_focus: Focus):
        """Emit start events and flag the node as resolving."""
        current_node = current_focus.node

        # Set the current node to resolving
        current_node.state = NodeResolutionState.RESOLVING
        # Inform the GUI which node is now the active focus before we announce processing start.
        focus_payload = CurrentDataNodeEvent(node_name=current_node.name)

        event_queue.put(
            ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=focus_payload))
        )
        event_queue.put(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
            )
        )
        logger.info("Node '%s' is processing.", current_node.name)
    
    @staticmethod
    def _mark_node_as_finished(context: ResolutionContext, current_focus: Focus):
        """Emit finished* events and flag the node as resolved."""
        current_node = current_focus.node
        logger.info("Node '%s' finished processing.", current_node.name)

        event_queue.put(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
            )
        )
        current_node.state = NodeResolutionState.RESOLVED
        details = f"'{current_node.name}' resolved."

        logger.info(details)

    @staticmethod
    def _serialization(context: ResolutionContext, current_focus: Focus):
        """Serialize node inputs/outputs for debug logging when log-level is DEBUG."""
        current_node = current_focus.node
        # Serialization can be slow so only do it if the user wants debug details.
        if logger.level <= logging.DEBUG:
            logger.debug(
                "INPUTS: %s\nOUTPUTS: %s",
                TypeValidator.safe_serialize(current_node.parameter_values),
                TypeValidator.safe_serialize(current_node.parameter_output_values),
            )
    
    @staticmethod
    def _pass_values_to_connected_nodes(context: ResolutionContext, current_focus: Focus):
        """Push parameter output values from the current node to all connected downstream nodes."""
        current_node = current_focus.node
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        for parameter_name, value in current_node.parameter_output_values.items():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Canceling flow run. Node '{current_node.name}' specified a Parameter '{parameter_name}', but no such Parameter could be found on that Node."
                raise KeyError(err)
            data_type = parameter.type
            if data_type is None:
                data_type = ParameterTypeBuiltin.NONE.value
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
            # Pass the value through to the new nodes.
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

    @staticmethod
    def _get_library_name(context: ResolutionContext, node: BaseNode) -> str | None:
        """Return the registered library that owns node if exactly one match is found."""
        library = LibraryRegistry.get_libraries_with_node_type(node.__class__.__name__)
        if len(library) == 1:
            return library[0]
        return None

    @staticmethod
    def _clear_parameter_output_values(context: ResolutionContext, current_node) -> None:
        """Clears all parameter output values for the currently focused node in the resolution context.

        This method iterates through each parameter output value stored in the current node,
        removes it from the node's parameter_output_values dictionary, and publishes an event
        to notify the system about the parameter value being set to None.

        Args:
            context (ResolutionContext): The resolution context containing the focus stack
                with the current node being processed.

        Raises:
            ValueError: If a parameter name in parameter_output_values doesn't correspond
                to an actual parameter in the node.

        Note:
            - Uses a copy of parameter_output_values to safely modify the dictionary during iteration
            - For each parameter, publishes a ParameterValueUpdateEvent with value=None
            - Events are wrapped in ExecutionGriptapeNodeEvent before publishing
        """
        for parameter_name in current_node.parameter_output_values.copy():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Attempted to execute node '{current_node.name}' but could not find parameter '{parameter_name}' that was indicated as having a value."
                raise ValueError(err)
            parameter_type = parameter.type
            if parameter_type is None:
                parameter_type = ParameterTypeBuiltin.NONE.value
            payload = ParameterValueUpdateEvent(
                node_name=current_node.name,
                parameter_name=parameter_name,
                data_type=parameter_type,
                value=None,
            )
            event_queue.put(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
        current_node.parameter_output_values.clear()