from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from griptape_nodes.machines.fsm import FSM, State
from src.griptape_nodes.retained_mode.managers.dag_orchestrator_example import DagOrchestrator, NodeState

logger = logging.getLogger("griptape_nodes")


@dataclass
class ExecutionContext:
    current_dag: DagOrchestrator
    error_message: str | None = None
    currently_running_nodes: list[DagOrchestrator.DagNode] = []

    def __init__(self) -> None:
        self.dag_state = {}
        self.error_message = None

    def reset(self) -> None:
        self.dag_state.clear()
        self.error_message = None


class ExecutionState(State):
    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        logger.info("Entering DAG execution state")
        return None

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:
        try:
            # DAG execution logic would go here
            logger.info("DAG execution in progress")
        except Exception as e:
            logger.error("DAG execution failed: %s", e)
            context.error_message = str(e)
            return ErrorState
        else:
            # For now, assume execution completes successfully
            return CompleteState


class ErrorState(State):
    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)
        context.currently_running_nodes = []
        for node in context.current_dag.node_to_reference.values():
            # Cancel all nodes that haven't yet begun processing.
            if node.node_state in [NodeState.WAITING, NodeState.QUEUED]:
                node.node_state = NodeState.CANCELED
            elif node.node_state == NodeState.PROCESSING:
                # Add nodes that are currently processing to this list
                context.currently_running_nodes.append(node)
        # Shut down and cancel all threads that haven't yet ran. Currently running threads will not be affected.
        context.current_dag.thread_executor.shutdown(wait=False, cancel_futures=True)
        return ErrorState

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:
        # Don't modify lists while iterating through them.
        for node in context.currently_running_nodes.copy():
            if node.thread_reference is not None:
                if node.thread_reference.done():
                    node.node_state = NodeState.DONE
                elif node.thread_reference.cancelled():
                    node.node_state = NodeState.CANCELED
                # remove the node from currently running nodes
                context.currently_running_nodes.remove(node)
                # Get rid of this future
                del node.thread_reference
        if not context.currently_running_nodes:
            # Finish up. We failed.
            return CompleteState
        # Let's continue going through until everything is cancelled.
        return ErrorState


class CompleteState(State):
    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        logger.info("DAG execution completed successfully")
        return None

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class DagExecutionMachine(FSM[ExecutionContext]):
    """State machine for DAG execution."""

    def __init__(self) -> None:
        execution_context = ExecutionContext()
        super().__init__(execution_context)

    def start_execution(self) -> None:
        self.start(ExecutionState)

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_error(self) -> bool:
        return self._current_state is ErrorState

    def get_error_message(self) -> str | None:
        return self._context.error_message

    def reset_machine(self) -> None:
        self._context.reset()
        self._current_state = None
