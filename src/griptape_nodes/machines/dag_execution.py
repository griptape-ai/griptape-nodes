from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import NodeResolvedEvent, ParameterValueUpdateEvent
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
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
    flow_name: str

    def __init__(self, flow_name: str, dag_instance: DagOrchestrator | None = None) -> None:
        self.flow_name = flow_name
        if dag_instance is not None:
            self.current_dag = dag_instance
        else:
            self.current_dag = GriptapeNodes.get_instance().DagManager().get_orchestrator_for_flow(flow_name)
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR

    def reset(self) -> None:
        self.current_dag.clear()
        self.workflow_state = WorkflowState.NO_ERROR
        self.error_message = None


class ExecutionState(State):
    @staticmethod
    def handle_done_nodes(done_node: DagOrchestrator.DagNode) -> None:
        current_node = done_node.node_reference
        # Publish all parameter updates.
        current_node.state = NodeResolutionState.RESOLVED
        # Serialization can be slow so only do it if the user wants debug details.
        if logger.level <= logging.DEBUG:
            logger.debug(
                "INPUTS: %s\nOUTPUTS: %s",
                TypeValidator.safe_serialize(current_node.parameter_values),
                TypeValidator.safe_serialize(current_node.parameter_output_values),
            )

        for parameter_name, value in current_node.parameter_output_values.items():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Canceling flow run. Node '{current_node.name}' specified a Parameter '{parameter_name}', but no such Parameter could be found on that Node."
                raise KeyError(err)
            data_type = parameter.type
            if data_type is None:
                data_type = ParameterTypeBuiltin.NONE.value
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(
                        payload=ParameterValueUpdateEvent(
                            node_name=current_node.name,
                            parameter_name=parameter_name,
                            data_type=data_type,
                            value=TypeValidator.safe_serialize(value),
                        )
                    ),
                )
            )
        # Output values should already be saved!
        library = LibraryRegistry.get_libraries_with_node_type(current_node.__class__.__name__)
        if len(library) == 1:
            library_name = library[0]
        else:
            library_name = None
        GriptapeNodes.EventManager().put_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=NodeResolvedEvent(
                        node_name=current_node.name,
                        parameter_output_values=TypeValidator.safe_serialize(current_node.parameter_output_values),
                        node_type=current_node.__class__.__name__,
                        specific_library_name=library_name,
                    )
                )
            )
        )

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
    def clear_parameter_output_values(node_reference: DagOrchestrator.DagNode) -> None:
        """Clear all parameter output values for the given node and publish events.

        This method iterates through each parameter output value stored in the node,
        removes it from the node's parameter_output_values dictionary, and publishes an event
        to notify the system about the parameter value being set to None.

        Args:
            node_reference (DagOrchestrator.DagNode): The DAG node to clear values for.

        Raises:
            ValueError: If a parameter name in parameter_output_values doesn't correspond
                to an actual parameter in the node.
        """
        current_node = node_reference.node_reference
        for parameter_name in current_node.parameter_output_values.copy():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Attempted to clear output values for node '{current_node.name}' but could not find parameter '{parameter_name}' that was indicated as having a value."
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
            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload))
            )
        current_node.parameter_output_values.clear()

    @staticmethod
    async def execute_node(current_node: DagOrchestrator.DagNode, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            await current_node.node_reference.aprocess()

    @staticmethod
    async def on_enter(context: ExecutionContext) -> type[State] | None:
        for node in context.current_dag.node_to_reference.values():
            # We have a DAG. Flag all nodes in DAG as queued. Workflow state is NO_ERROR
            node.node_state = NodeState.QUEUED
        context.workflow_state = WorkflowState.NO_ERROR
        return ExecutionState

    @staticmethod
    def build_node_states(context: ExecutionContext) -> tuple[list[str], list[str], list[str], list[str]]:
        network = context.current_dag.network
        leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]
        done_nodes = []
        canceled_nodes = []
        queued_nodes = []
        for node in leaf_nodes:
            node_reference = context.current_dag.node_to_reference[node]
            # If the node is locked, mark it as done so it skips execution
            if node_reference.node_reference.lock:
                node_reference.node_state = NodeState.DONE
                done_nodes.append(node)
                continue
            node_state = node_reference.node_state
            if node_state == NodeState.DONE:
                done_nodes.append(node)
            elif node_state == NodeState.CANCELED:
                canceled_nodes.append(node)
            elif node_state == NodeState.QUEUED:
                queued_nodes.append(node)
        return done_nodes, canceled_nodes, queued_nodes, leaf_nodes

    @staticmethod
    async def on_update(context: ExecutionContext) -> type[State] | None:
        # Do we have any Leaf Nodes not in canceled state?
        network = context.current_dag.network
        # Check and see if there are leaf nodes that are cancelled.
        done_nodes, canceled_nodes, queued_nodes, leaf_nodes = ExecutionState.build_node_states(context)
        # Are there any nodes in Done state?
        for node in done_nodes:
            # We have nodes in done state.
            # Remove the leaf node from the graph.
            network.remove_node(node)
            # Return thread to thread pool.
            ExecutionState.handle_done_nodes(context.current_dag.node_to_reference[node])
        # Reinitialize leaf nodes since maybe we changed things up.
        if len(done_nodes) > 0:
            # We removed nodes from the network. There may be new leaf nodes.
            done_nodes, canceled_nodes, queued_nodes, leaf_nodes = ExecutionState.build_node_states(context)
        # We have no more leaf nodes. Quit early.
        if not leaf_nodes:
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return CompleteState
        if len(canceled_nodes) == len(leaf_nodes):
            # All leaf nodes are cancelled.
            # Set state to workflow complete.
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return CompleteState
        # Are there any in the queued state?
        for node in queued_nodes:
            # Process all queued nodes - the async semaphore will handle concurrency limits
            node_reference = context.current_dag.node_to_reference[node]

            # Collect parameter values from upstream nodes before executing
            try:
                ExecutionState.collect_values_from_upstream_nodes(node_reference)
            except Exception as e:
                logger.exception("Error collecting parameter values for node '%s'", node_reference.node_reference.name)
                context.error_message = (
                    f"Parameter passthrough failed for node '{node_reference.node_reference.name}': {e}"
                )
                context.workflow_state = WorkflowState.ERRORED
                return ErrorState

            # Clear parameter output values before execution
            try:
                ExecutionState.clear_parameter_output_values(node_reference)
            except Exception as e:
                logger.exception(
                    "Error clearing parameter output values for node '%s'", node_reference.node_reference.name
                )
                context.error_message = (
                    f"Parameter clearing failed for node '{node_reference.node_reference.name}': {e}"
                )
                context.workflow_state = WorkflowState.ERRORED
                return ErrorState

            def on_task_done(task: asyncio.Task) -> None:
                logger.error("Task done")
                node = context.current_dag.task_to_node.pop(task)
                node.node_state = NodeState.DONE
                logger.error("Task done: %s", node.node_reference.name)

            # Execute the node asynchronously
            node_task = asyncio.create_task(
                ExecutionState.execute_node(node_reference, context.current_dag.async_semaphore)
            )
            # Add a callback to set node to done when task has finished.
            context.current_dag.task_to_node[node_task] = node_reference
            node_reference.task_reference = node_task
            node_task.add_done_callback(lambda t: on_task_done(t))
            node_reference.node_state = NodeState.PROCESSING
            node_reference.node_reference.state = NodeResolutionState.RESOLVING
            # Wait for a task to finish
        await asyncio.wait(context.current_dag.task_to_node.keys(), return_when=asyncio.FIRST_COMPLETED)
        # Infinite loop? let's see how this goes.
        return ExecutionState


class ErrorState(State):
    @staticmethod
    async def on_enter(context: ExecutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)
        for node in context.current_dag.node_to_reference.values():
            # Cancel all nodes that haven't yet begun processing.
            if node.node_state == NodeState.QUEUED:
                node.node_state = NodeState.CANCELED
        # Shut down and cancel all threads/tasks that haven't yet ran. Currently running ones will not be affected.
        # Cancel async tasks
        for task in list(context.current_dag.task_to_node.keys()):
            if not task.done():
                task.cancel()
        return ErrorState

    @staticmethod
    async def on_update(context: ExecutionContext) -> type[State] | None:
        # Don't modify lists while iterating through them.
        task_to_node = context.current_dag.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        # Handle async tasks
        task_to_node = context.current_dag.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        if len(task_to_node) == 0 and len(task_to_node) == 0:
            # Finish up. We failed.
            context.workflow_state = WorkflowState.ERRORED
            return CompleteState
        # Let's continue going through until everything is cancelled.
        return ErrorState


class CompleteState(State):
    @staticmethod
    async def on_enter(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        logger.info("DAG execution completed successfully")
        return None

    @staticmethod
    async def on_update(context: ExecutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class DagExecutionMachine(FSM[ExecutionContext]):
    """State machine for DAG execution."""

    def __init__(self, flow_name: str, dag_instance: DagOrchestrator | None = None) -> None:
        execution_context = ExecutionContext(flow_name, dag_instance)
        super().__init__(execution_context)

    async def start_execution(self) -> None:
        await self.start(ExecutionState)

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_error(self) -> bool:
        return self._current_state is ErrorState

    def get_error_message(self) -> str | None:
        return self._context.error_message

    def reset_machine(self) -> None:
        self._context.reset()
        self._current_state = None
