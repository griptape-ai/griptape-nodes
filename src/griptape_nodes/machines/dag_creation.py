from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.parallel_execution import ParallelExecutionMachine
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    ParameterSpotlightEvent,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.dag_orchestrator import DagOrchestrator

logger = logging.getLogger("griptape_nodes")


@dataclass
class Focus:
    node: BaseNode
    scheduled_value: Any | None = None


class DagCreationContext:
    focus_stack: list[Focus]
    paused: bool
    execution_machine: ParallelExecutionMachine
    flow_name: str
    build_only: bool
    batched_nodes: list[BaseNode]

    def __init__(self, flow_name: str) -> None:
        self.flow_name = flow_name
        self.focus_stack = []
        self.paused = False
        self.build_only = False
        self.batched_nodes = []
        # Get the DAG instance that will be used throughout resolution and execution

        dag_instance = GriptapeNodes.get_instance().DagManager().get_orchestrator_for_flow(flow_name)
        self.execution_machine = ParallelExecutionMachine(flow_name, dag_instance)

    def reset(self, *, cancel: bool = False) -> None:
        if self.focus_stack:
            node = self.focus_stack[-1].node
            node.clear_node()
        self.focus_stack.clear()
        self.paused = False
        self.execution_machine.reset_machine(cancel=cancel)


class InitializeDagSpotlightState(State):
    @staticmethod
    async def on_enter(context: DagCreationContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=current_node.name))
            )
        )
        if not context.paused:
            return InitializeDagSpotlightState
        return None

    @staticmethod
    async def on_update(context: DagCreationContext) -> type[State] | None:
        if not len(context.focus_stack):
            return DagCompleteState
        current_node = context.focus_stack[-1].node
        if current_node.state == NodeResolutionState.UNRESOLVED:
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
    async def on_enter(context: DagCreationContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        current_parameter = current_node.get_current_parameter()
        if current_parameter is None:
            return BuildDagNodeState
        GriptapeNodes.EventManager().put_event(
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
    async def on_update(context: DagCreationContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        current_parameter = current_node.get_current_parameter()
        connections = GriptapeNodes.FlowManager().get_connections()
        if current_parameter is None:
            msg = "No current parameter set."
            raise ValueError(msg)
        next_node = connections.get_connected_node(current_node, current_parameter)
        if next_node:
            next_node, _ = next_node
        if next_node:
            dag_instance = GriptapeNodes.get_instance().DagManager().get_orchestrator_for_flow(context.flow_name)
            if next_node.state == NodeResolutionState.UNRESOLVED:
                focus_stack_names = {focus.node.name for focus in context.focus_stack}
                if next_node.name in focus_stack_names:
                    msg = f"Cycle detected between node '{current_node.name}' and '{next_node.name}'."
                    raise RuntimeError(msg)
                dag_instance.network.add_edge(next_node.name, current_node.name)
                context.focus_stack.append(Focus(node=next_node))
                return InitializeDagSpotlightState
            if next_node.state == NodeResolutionState.RESOLVED and next_node in context.batched_nodes:
                dag_instance.network.add_edge(next_node.name, current_node.name)
        if current_node.advance_parameter():
            return InitializeDagSpotlightState
        return BuildDagNodeState


class BuildDagNodeState(State):
    @staticmethod
    async def on_enter(context: DagCreationContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node

        dag_instance = GriptapeNodes.get_instance().DagManager().get_orchestrator_for_flow(context.flow_name)

        # Add the current node to the DAG using get_instance() pattern
        node_reference = DagOrchestrator.DagNode(node_reference=current_node)
        dag_instance.node_to_reference[current_node.name] = node_reference
        # Add node name to DAG (has to be a hashable value)
        dag_instance.network.add_node(node_for_adding=current_node.name)

        if not context.paused:
            return BuildDagNodeState
        return None

    @staticmethod
    async def on_update(context: DagCreationContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node

        # Mark node as resolved for DAG building purposes
        current_node.state = NodeResolutionState.RESOLVED
        # Add to batched nodes
        context.batched_nodes.append(current_node)

        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateDagParameterState

        if context.build_only:
            return DagCompleteState
        return ExecuteDagState


class ExecuteDagState(State):
    @staticmethod
    async def on_enter(context: DagCreationContext) -> type[State] | None:
        # Start DAG execution after resolution is complete
        context.batched_nodes.clear()
        await context.execution_machine.start_execution()
        if not context.paused:
            return ExecuteDagState
        return None

    @staticmethod
    async def on_update(context: DagCreationContext) -> type[State] | None:
        # Check if DAG execution is complete
        if context.execution_machine.is_complete():
            return DagCompleteState
        if context.execution_machine.is_error():
            return DagCompleteState
        await context.execution_machine.update()
        execution_complete_after_update = context.execution_machine.is_complete()
        execution_error_after_update = context.execution_machine.is_error()
        logger.debug(
            "After update - execution_complete: %s, execution_error: %s",
            execution_complete_after_update,
            execution_error_after_update,
        )

        if execution_complete_after_update:
            logger.debug("DAG execution completed after update - transitioning to DagCompleteState")
            return DagCompleteState
        if execution_error_after_update:
            logger.warning("DAG execution encountered error after update - transitioning to DagCompleteState")
            return DagCompleteState

        return None


class DagCompleteState(State):
    @staticmethod
    async def on_enter(context: DagCreationContext) -> type[State] | None:
        # Set build_only back to False.
        context.build_only = False
        return None

    @staticmethod
    async def on_update(context: DagCreationContext) -> type[State] | None:  # noqa: ARG004
        return None


class DagCreationMachine(FSM[DagCreationContext]):
    """State machine for building DAG structure without execution."""

    def __init__(self, flow_name: str) -> None:
        resolution_context = DagCreationContext(flow_name)
        super().__init__(resolution_context)

    async def resolve_node(self, node: BaseNode, *, build_only: bool = False) -> None:
        """Build DAG structure starting from the given node."""
        self._context.focus_stack.append(Focus(node=node))
        self._context.build_only = build_only
        await self.start(InitializeDagSpotlightState)

    async def build_dag_for_node(self, node: BaseNode) -> None:
        """Build DAG structure starting from the given node. (Deprecated: use resolve_node)."""
        await self.resolve_node(node)

    def change_debug_mode(self, *, debug_mode: bool) -> None:
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is DagCompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def get_context(self) -> DagCreationContext:
        return self._context

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None

    def get_current_state(self) -> State | None:
        return self._current_state

    def set_current_state(self, value: State | None) -> None:
        self._current_state = value
