from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from griptape.events import EventBus
from griptape.utils import with_contextvars

from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    ResumeNodeProcessingEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger

if TYPE_CHECKING:
    import threading
    from concurrent.futures import Future
from griptape_nodes.retained_mode.managers.dag_orchestrator import DagOrchestrator, NodeState


class WorkflowState(Enum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"


@dataclass
class ExecutionContext:
    current_dag: DagOrchestrator
    error_message: str | None
    workflow_state: WorkflowState

    def __init__(self) -> None:
        self.current_dag = GriptapeNodes.get_instance().DagManager()
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR

    def reset(self) -> None:
        self.current_dag.clear()
        self.workflow_state = WorkflowState.NO_ERROR
        self.error_message = None


class ExecutionState(State):
    @staticmethod
    def handle_done_nodes(context: ExecutionContext, done_node: DagOrchestrator.DagNode) -> None:
        node = done_node.node_reference
        # Publish all parameter updates.
        for parameter, value in node.parameter_output_values.items():
            node.publish_update_to_parameter(parameter,value)

    @staticmethod
    def collect_values_from_upstream_nodes(node_reference: DagOrchestrator.DagNode) -> None:
        """Collect output values from resolved upstream nodes and pass them to the current node.

        This method iterates through all input parameters of the current node, finds their
        connected upstream nodes, and if those nodes are resolved, retrieves their output
        values and passes them through using SetParameterValueRequest.

        Args:
            node_reference (DagOrchestrator.DagNode): The node to collect values for.
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        current_node = node_reference.node_reference
        connections = GriptapeNodes.FlowManager().get_connections()

        for parameter in current_node.parameters:
            # Skip control type parameters
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue

            # Get the connected upstream node for this parameter
            upstream_connection = connections.get_connected_node(current_node, parameter)
            if upstream_connection:
                upstream_node, upstream_parameter = upstream_connection

                # If the upstream node is resolved, collect its output value
                if upstream_parameter.name in upstream_node.parameter_output_values:
                    output_value = upstream_node.parameter_output_values[upstream_parameter.name]
                else:
                    output_value = upstream_node.get_parameter_value(upstream_parameter.name)

                # Pass the value through using the same mechanism as normal resolution
                GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=parameter.name,
                        node_name=current_node.name,
                        value=output_value,
                        data_type=upstream_parameter.output_type,
                    )
                )

    @staticmethod
    def execute_node(current_node: DagOrchestrator.DagNode, sem: threading.Semaphore) -> None:
        import threading
        with sem:
            node_name = current_node.node_reference.name
            thread_name = threading.current_thread().name
            logger.info("THREAD_DEBUG: Starting process() for node '%s' in thread '%s'", node_name, thread_name)
            logger.info("THREAD_DEBUG: Node '%s' parameter_output_values BEFORE process(): %s", 
                       node_name, list(current_node.node_reference.parameter_output_values.keys()))
            
            current_node.node_reference.process()
            
            logger.info("THREAD_DEBUG: Completed process() for node '%s' in thread '%s'", node_name, thread_name)
            logger.info("THREAD_DEBUG: Node '%s' parameter_output_values AFTER process(): %s", 
                       node_name, list(current_node.node_reference.parameter_output_values.keys()))
            logger.info("THREAD_DEBUG: Node '%s' parameter_output_values contents: %s", 
                       node_name, {k: str(v)[:100] + "..." if len(str(v)) > 100 else str(v) 
                                  for k, v in current_node.node_reference.parameter_output_values.items()})

    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:
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
            if context.current_dag.sem.acquire(blocking=False):
                # we have threads available
                node_reference = context.current_dag.node_to_reference[node]

                # Collect parameter values from upstream nodes before executing
                try:
                    logger.info("THREAD_DEBUG: About to collect parameter values for node '%s' in main thread", node_reference.node_reference.name)
                    ExecutionState.collect_values_from_upstream_nodes(node_reference)
                    logger.info("THREAD_DEBUG: Completed parameter collection for node '%s' in main thread", node_reference.node_reference.name)
                except Exception as e:
                    logger.exception("Error collecting parameter values for node '%s'", node_reference.node_reference.name)
                    context.error_message = f"Parameter passthrough failed for node '{node_reference.node_reference.name}': {e}"
                    context.workflow_state = WorkflowState.ERRORED
                    context.current_dag.sem.release()  # Release the semaphore we just acquired
                    return ErrorState

                def on_future_done(future: Future) -> None:
                    # TODO: Will this call the correct thing?
                    node = context.current_dag.future_to_node.pop(future)
                    node.node_state = NodeState.DONE
                    # Publish event to resume DAG execution
                    EventBus.publish_event(
                        ExecutionGriptapeNodeEvent(
                            wrapped_event=ExecutionEvent(
                                payload=ResumeNodeProcessingEvent(node_name=node.node_reference.name)
                            )
                        )
                    )

                logger.info("THREAD_DEBUG: Submitting node '%s' to thread executor from main thread", node_reference.node_reference.name)
                node_future = context.current_dag.thread_executor.submit(
                    ExecutionState.execute_node, node_reference, context.current_dag.sem
                )
                logger.info("THREAD_DEBUG: Node '%s' submitted to thread executor successfully", node_reference.node_reference.name)
                # Add a callback to set node to done when future has finished.
                context.current_dag.future_to_node[node_future] = node_reference
                node_reference.thread_reference = node_future
                node_reference.node_state = NodeState.PROCESSING
                node_future.add_done_callback(with_contextvars(on_future_done))
                # Map futures to nodes.
        # Exit out to None. Wait to reenter.
        return None


class ErrorState(State):
    @staticmethod
    def on_enter(context: ExecutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)
        for node in context.current_dag.node_to_reference.values():
            # Cancel all nodes that haven't yet begun processing.
            if node.node_state == NodeState.QUEUED:
                node.node_state = NodeState.CANCELED
        # Shut down and cancel all threads that haven't yet ran. Currently running threads will not be affected.
        context.current_dag.thread_executor.shutdown(wait=False, cancel_futures=True)
        return ErrorState

    @staticmethod
    def on_update(context: ExecutionContext) -> type[State] | None:
        # Don't modify lists while iterating through them.
        future_to_node = context.current_dag.future_to_node
        for future, node in future_to_node.copy().items():
            if future.done():
                node.node_state = NodeState.DONE
            elif future.cancelled():
                node.node_state = NodeState.CANCELED
            future_to_node.pop(future)
        if len(future_to_node) == 0:
            # Finish up. We failed.
            context.workflow_state = WorkflowState.ERRORED
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
