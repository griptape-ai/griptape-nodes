from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any
import time

from griptape_nodes.app.app_sessions import event_queue
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.machines.execute_node import ExecuteNodeState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.execution_utils import ResolutionContext
from griptape_nodes.machines.execution_utils import CompleteState
from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.retained_mode.events.base_events import ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent
from griptape_nodes.retained_mode.events.execution_events import NodeFinishProcessEvent

logger = logging.getLogger("griptape_nodes")


class EvaluateParameterState(State):
    """State for evaluating parameters and building the dependency graph."""

    @staticmethod
    def add_dependencies_to_graph(current_node: BaseNode, context: ResolutionContext):
        """Recursively add all dependencies of the current node to the DAG."""
        current_node.initialize_spotlight()

        while current_node.current_spotlight_parameter is not None:
            # Get connections using FlowManaager
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            connections = GriptapeNodes.FlowManager().get_connections()

            # Run the get_connected_node method and retrieve the node
            connected_node_and_parameter = connections.get_connected_node(current_node, current_node.current_spotlight_parameter)
            if connected_node_and_parameter is not None:
                (connected_node, _) = connected_node_and_parameter

                if connected_node in context.DAG.graph[current_node]:
                    # Check if there is a cycle, aka nodes that depend on each other to run
                    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                    GriptapeNodes.FlowManager().cancel_flow_run()
                    raise RuntimeError(f"Cycle detected between node {current_node.name} and {connected_node.name}")

                context.DAG.add_node(connected_node)
                context.DAG.add_edge(connected_node, current_node)
                # Recursively call the function on the connected node to check if it has dependencies
                EvaluateParameterState.add_dependencies_to_graph(connected_node, context)
            current_node.advance_parameter()

    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        """Enter the EvaluateParameterState."""
        return EvaluateParameterState

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        """Update the state by building the dependency graph and logging ready nodes."""
        if isinstance(context.root_node_resolving, BaseNode):
            context.DAG.add_node(context.root_node_resolving)
            EvaluateParameterState.add_dependencies_to_graph(context.root_node_resolving, context)
        # log debug info about DAG
        logger.info("DAG Built, All Nodes: %s", [node.name for node in context.DAG.get_all_nodes()])
        logger.info("DAG Built, Ready Nodes: %s", [node.name for node in context.DAG.get_ready_nodes()])
        return ExecuteNodeState


class NodeResolutionMachine(FSM[ResolutionContext]):
    """Finite state machine for resolving nodes and their dependencies."""
    def __init__(self) -> None:
        """Initialize the node resolution machine with a new context."""
        resolution_context = ResolutionContext()
        super().__init__(resolution_context)

    def resolve_node(self, node: BaseNode) -> None:
        """Resolve the given node and its dependencies."""
        self._context.root_node_resolving = node
        self.start(EvaluateParameterState)

    def change_debug_mode(self, debug_mode: bool) -> None:
        """Change the debug mode for the resolution machine."""
        self._debug_mode = debug_mode

    def is_complete(self) -> bool:
        """Return True if the resolution is complete."""
        return (self._current_state == CompleteState)

    def is_started(self) -> bool:
        """Return True if the resolution has started."""
        return self._current_state is not None

    def reset_machine(self) -> None:
        """Reset the resolution machine to its initial state."""
        self._context.reset()
        self._current_state = None