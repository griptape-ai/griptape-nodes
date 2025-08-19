from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    ParameterSpotlightEvent,
)
from src.griptape_nodes.retained_mode.managers.dag_orchestrator_example import DagOrchestrator

logger = logging.getLogger("griptape_nodes")


@dataclass
class Focus:
    node: BaseNode
    scheduled_value: Any | None = None


class DagResolutionContext:
    focus_stack: list[Focus]
    paused: bool

    def __init__(self) -> None:
        self.focus_stack = []
        self.paused = False

    def reset(self) -> None:
        if self.focus_stack:
            node = self.focus_stack[-1].node
            node.clear_node()
        self.focus_stack.clear()
        self.paused = False


class InitializeDagSpotlightState(State):
    @staticmethod
    def on_enter(context: DagResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=current_node.name))
            )
        )
        if not context.paused:
            return InitializeDagSpotlightState
        return None

    @staticmethod
    def on_update(context: DagResolutionContext) -> type[State] | None:
        if not len(context.focus_stack):
            return DagCompleteState
        current_node = context.focus_stack[-1].node
        if current_node.state == NodeResolutionState.UNRESOLVED:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.FlowManager().get_connections().unresolve_future_nodes(current_node)
            current_node.initialize_spotlight()
        current_node.state = NodeResolutionState.RESOLVING
        if current_node.get_current_parameter() is None:
            if current_node.advance_parameter():
                return EvaluateDagParameterState
            return BuildDagNodeState
        return EvaluateDagParameterState


class EvaluateDagParameterState(State):
    @staticmethod
    def on_enter(context: DagResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        current_parameter = current_node.get_current_parameter()
        if current_parameter is None:
            return BuildDagNodeState
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=ParameterSpotlightEvent(
                        node_name=current_node.name,
                        parameter_name=current_parameter.name,
                    )
                )
            )
        )
        if not context.paused:
            return EvaluateDagParameterState
        return None

    @staticmethod
    def on_update(context: DagResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        current_parameter = current_node.get_current_parameter()
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        if current_parameter is None:
            msg = "No current parameter set."
            raise ValueError(msg)
        next_node = connections.get_connected_node(current_node, current_parameter)
        if next_node:
            next_node, _ = next_node
        if next_node and next_node.state == NodeResolutionState.UNRESOLVED:
            focus_stack_names = {focus.node.name for focus in context.focus_stack}
            if next_node.name in focus_stack_names:
                msg = f"Cycle detected between node '{current_node.name}' and '{next_node.name}'."
                raise RuntimeError(msg)

            context.focus_stack.append(Focus(node=next_node))
            return InitializeDagSpotlightState

        if current_node.advance_parameter():
            return InitializeDagSpotlightState
        return BuildDagNodeState


class BuildDagNodeState(State):
    @staticmethod
    def collect_dag_connections(context: DagResolutionContext) -> None:
        """Build DAG connections by analyzing upstream nodes without executing them."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        current_node = context.focus_stack[-1].node
        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue

            upstream_connection = connections.get_connected_node(current_node, parameter)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # Add the edge to the DAG - this is the key DAG building step
                dag_instance = DagOrchestrator.get_instance()
                DagOrchestrator.network.add_edge(upstream_node.name, current_node.name)
                logger.info(
                    "DAG BUILD: Added edge '%s' -> '%s'. Network now has %d edges. Instance ID: %s",
                    upstream_node.name,
                    current_node.name,
                    len(DagOrchestrator.network.edges()),
                    id(dag_instance),
                )

    @staticmethod
    def on_enter(context: DagResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node

        # Add the current node to the DAG using get_instance() pattern
        dag_instance = DagOrchestrator.get_instance()
        node_reference = DagOrchestrator.DagNode(node_reference=current_node)
        DagOrchestrator.node_to_reference[current_node.name] = node_reference
        # Add node name to DAG (has to be a hashable value)
        DagOrchestrator.network.add_node(node_for_adding=current_node.name)

        # Debug logging to track DAG building
        logger.info(
            "DAG BUILD: Added node '%s' to network. Network now has %d nodes, %d edges. Instance ID: %s",
            current_node.name,
            len(DagOrchestrator.network.nodes()),
            len(DagOrchestrator.network.edges()),
            id(dag_instance),
        )

        # Build DAG connections
        BuildDagNodeState.collect_dag_connections(context)

        if not context.paused:
            return BuildDagNodeState
        return None

    @staticmethod
    def on_update(context: DagResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node

        # Mark node as resolved for DAG building purposes
        current_node.state = NodeResolutionState.RESOLVED
        logger.info("DAG node '%s' added to graph.", current_node.name)

        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateDagParameterState

        return DagCompleteState


class DagCompleteState(State):
    @staticmethod
    def on_enter(context: DagResolutionContext) -> type[State] | None:
        return None

    @staticmethod
    def on_update(context: DagResolutionContext) -> type[State] | None:
        return None


class DagResolutionMachine(FSM[DagResolutionContext]):
    """State machine for building DAG structure without execution."""

    def __init__(self) -> None:
        resolution_context = DagResolutionContext()
        super().__init__(resolution_context)

    def build_dag_for_node(self, node: BaseNode) -> None:
        """Build DAG structure starting from the given node."""
        self._context.focus_stack.append(Focus(node=node))
        self.start(InitializeDagSpotlightState)

    def change_debug_mode(self, debug_mode: bool) -> None:
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is DagCompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self) -> None:
        self._context.reset()
        self._current_state = None
