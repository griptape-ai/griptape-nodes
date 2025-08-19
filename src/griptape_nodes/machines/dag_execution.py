from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from griptape_nodes.machines.fsm import FSM, State
from src.griptape_nodes.retained_mode.managers.dag_orchestrator_example import DagOrchestrator

logger = logging.getLogger("griptape_nodes")


@dataclass
class ExecutionContext:
    current_dag: DagOrchestrator
    error_message: str | None = None

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
        return None

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        return None


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
