from __future__ import annotations

from concurrent.futures import thread
from enum import Enum
import logging
from dataclasses import dataclass
import queue
from typing import Any

from griptape_nodes.machines.fsm import FSM, State
from src.griptape_nodes.retained_mode.managers.dag_orchestrator_example import DagOrchestrator, NodeState

logger = logging.getLogger("griptape_nodes")

class WorkflowState(Enum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"


@dataclass
class ExecutionContext:
    current_dag: DagOrchestrator
    error_message: str | None
    currently_running_nodes: list[DagOrchestrator.DagNode]
    workflow_state: WorkflowState

    def __init__(self) -> None:
        self.dag_state = {}
        self.error_message = None
        self.currently_running_nodes = []
        self.workflow_state = WorkflowState.NO_ERROR

    def reset(self) -> None:
        self.dag_state.clear()
        self.error_message = None


class ExecutionState(State):

    @staticmethod
    def handle_done_nodes(context:ExecutionContext, done_node: DagOrchestrator.DagNode) -> None:
        pass

    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        logger.info("Entering DAG execution state")
        for node in context.current_dag.node_to_reference.values():
            # We have a DAG. Flag all nodes in DAG as queued. Workflow state is NO_ERROR
            node.node_state = NodeState.QUEUED
        context.workflow_state = WorkflowState.NO_ERROR
        return ExecutionState

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:
        # Do we have any Leaf Nodes not in canceled state?
        network = context.current_dag.network
        # Check and see if there are leaf nodes that are cancelled.
        leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]
        # We have no more leaf nodes. Quit early.
        if not leaf_nodes:
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return CompleteState
        done_nodes = []
        canceled_nodes = []
        queued_nodes = []
        # Get the status of all of the leaf nodes.
        for node in leaf_nodes:
            node_state = context.current_dag.node_to_reference[node].node_state
            if node_state == NodeState.CANCELED:
                canceled_nodes.append(node)
            elif node_state == NodeState.DONE:
                done_nodes.append(node)
            elif node_state == NodeState.QUEUED:
                queued_nodes.append(node)
        if len(canceled_nodes) == len(leaf_nodes):
            # All leaf nodes are cancelled.
            # Set state to workflow complete.
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return CompleteState
        # Are there any nodes in Done state?
        for node in done_nodes:
            # We have nodes in done state.
            # Remove the leaf node from the graph.
            network.remove_node(node)
            # Return thread to thread pool.
            ExecutionState.handle_done_nodes(context, context.current_dag.node_to_reference[node])
        # Are there any in the queued state?
        for node in queued_nodes:
            # Do we have any threads available?
            threads_available = context.current_dag.thread_executor._max_workers
        return ExecutionState


class ErrorState(State):
    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)
        context.currently_running_nodes = []
        for node in context.current_dag.node_to_reference.values():
            # Cancel all nodes that haven't yet begun processing.
            if node.node_state == NodeState.QUEUED:
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
