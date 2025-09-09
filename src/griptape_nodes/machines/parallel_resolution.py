from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.core_types import ParameterType, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.dag_builder import NodeState
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeResolvedEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

if TYPE_CHECKING:
    from griptape_nodes.common.directed_graph import DirectedGraph
    from griptape_nodes.machines.dag_builder import DagBuilder, DagNode

logger = logging.getLogger("griptape_nodes")


class WorkflowState(StrEnum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"
    CANCELED = "canceled"


class ParallelResolutionContext:
    paused: bool
    flow_name: str
    error_message: str | None
    workflow_state: WorkflowState
    # Execution fields
    async_semaphore: asyncio.Semaphore
    task_to_node: dict[asyncio.Task, DagNode]
    dag_builder: DagBuilder | None

    def __init__(
        self, flow_name: str, max_nodes_in_parallel: int | None = None, dag_builder: DagBuilder | None = None
    ) -> None:
        self.flow_name = flow_name
        self.paused = False
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR
        self.dag_builder = dag_builder

        # Initialize execution fields
        max_nodes_in_parallel = max_nodes_in_parallel if max_nodes_in_parallel is not None else 5
        self.async_semaphore = asyncio.Semaphore(max_nodes_in_parallel)
        self.task_to_node = {}

    @property
    def network(self) -> DirectedGraph:
        """Get network from dag_builder if available."""
        if not self.dag_builder:
            msg = "DagBuilder is not initialized"
            raise ValueError(msg)
        return self.dag_builder.graph

    @property
    def node_to_reference(self) -> dict[str, DagNode]:
        """Get node_to_reference from dag_builder if available."""
        if not self.dag_builder:
            msg = "DagBuilder is not initialized"
            raise ValueError(msg)
        return self.dag_builder.node_to_reference

    def reset(self, *, cancel: bool = False) -> None:
        self.paused = False
        if cancel:
            self.workflow_state = WorkflowState.CANCELED
            for node in self.node_to_reference.values():
                node.node_state = NodeState.CANCELED
        else:
            self.workflow_state = WorkflowState.NO_ERROR
            self.error_message = None
            self.network.clear()
            self.node_to_reference.clear()
            self.task_to_node.clear()


class ExecuteDagState(State):
    @staticmethod
    async def handle_done_nodes(done_node: DagNode) -> None:
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
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            await GriptapeNodes.EventManager().aput_event(
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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        await GriptapeNodes.EventManager().aput_event(
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
    async def collect_values_from_upstream_nodes(node_reference: DagNode) -> None:
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
                # Skip propagation for Control Parameters as they should not receive values
                if (
                    ParameterType.attempt_get_builtin(upstream_parameter.output_type)
                    != ParameterTypeBuiltin.CONTROL_TYPE
                ):
                    await GriptapeNodes.get_instance().ahandle_request(
                        SetParameterValueRequest(
                            parameter_name=parameter.name,
                            node_name=current_node.name,
                            value=output_value,
                            data_type=upstream_parameter.output_type,
                            incoming_connection_source_node_name=upstream_node.name,
                            incoming_connection_source_parameter_name=upstream_parameter.name,
                        )
                    )

    @staticmethod
    def build_node_states(context: ParallelResolutionContext) -> tuple[list[str], list[str], list[str], list[str]]:
        network = context.network
        leaf_nodes = [n for n in network.nodes() if network.in_degree(n) == 0]
        done_nodes = []
        canceled_nodes = []
        queued_nodes = []
        for node in leaf_nodes:
            node_reference = context.node_to_reference[node]
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
    async def execute_node(current_node: DagNode, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            await current_node.node_reference.aprocess()

    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        # Start DAG execution after resolution is complete
        for node in context.node_to_reference.values():
            # Only queue nodes that are waiting - preserve state of already processed nodes.
            if node.node_state == NodeState.WAITING:
                node.node_state = NodeState.QUEUED

        context.workflow_state = WorkflowState.NO_ERROR

        if not context.paused:
            return ExecuteDagState
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: C901, PLR0911
        # Check if execution is paused
        if context.paused:
            return None

        # Check if DAG execution is complete
        network = context.network
        # Check and see if there are leaf nodes that are cancelled.
        done_nodes, canceled_nodes, queued_nodes, leaf_nodes = ExecuteDagState.build_node_states(context)
        # Are there any nodes in Done state?
        for node in done_nodes:
            # We have nodes in done state.
            # Remove the leaf node from the graph.
            network.remove_node(node)
            # Return thread to thread pool.
            await ExecuteDagState.handle_done_nodes(context.node_to_reference[node])
        # Reinitialize leaf nodes since maybe we changed things up.
        if len(done_nodes) > 0:
            # We removed nodes from the network. There may be new leaf nodes.
            done_nodes, canceled_nodes, queued_nodes, leaf_nodes = ExecuteDagState.build_node_states(context)
        # We have no more leaf nodes. Quit early.
        if not leaf_nodes:
            context.workflow_state = WorkflowState.WORKFLOW_COMPLETE
            return DagCompleteState
        if len(canceled_nodes) == len(leaf_nodes):
            # All leaf nodes are cancelled.
            # Set state to workflow complete.
            context.workflow_state = WorkflowState.CANCELED
            return DagCompleteState
        # Are there any in the queued state?
        for node in queued_nodes:
            # Process all queued nodes - the async semaphore will handle concurrency limits
            node_reference = context.node_to_reference[node]

            # Collect parameter values from upstream nodes before executing
            try:
                await ExecuteDagState.collect_values_from_upstream_nodes(node_reference)
            except Exception as e:
                logger.exception("Error collecting parameter values for node '%s'", node_reference.node_reference.name)
                context.error_message = (
                    f"Parameter passthrough failed for node '{node_reference.node_reference.name}': {e}"
                )
                context.workflow_state = WorkflowState.ERRORED
                return ErrorState

            # Clear all of the current output values but don't broadcast the clearing.
            # to avoid any flickering in subscribers (UI).
            node_reference.node_reference.parameter_output_values.silent_clear()
            exceptions = node_reference.node_reference.validate_before_node_run()
            if exceptions:
                msg = f"Canceling flow run. Node '{node_reference.node_reference.name}' encountered problems: {exceptions}"
                logger.error(msg)
                return ErrorState

            def on_task_done(task: asyncio.Task) -> None:
                node = context.task_to_node.pop(task)
                node.node_state = NodeState.DONE

            # Execute the node asynchronously
            node_task = asyncio.create_task(ExecuteDagState.execute_node(node_reference, context.async_semaphore))
            # Add a callback to set node to done when task has finished.
            context.task_to_node[node_task] = node_reference
            node_reference.task_reference = node_task
            node_task.add_done_callback(lambda t: on_task_done(t))
            node_reference.node_state = NodeState.PROCESSING
            node_reference.node_reference.state = NodeResolutionState.RESOLVING

            # Send an event that this is a current data node:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            await GriptapeNodes.EventManager().aput_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=CurrentDataNodeEvent(node_name=node)))
            )
            # Wait for a task to finish
        await asyncio.wait(context.task_to_node.keys(), return_when=asyncio.FIRST_COMPLETED)
        # Once a task has finished, loop back to the top.
        if context.paused:
            return None
        return ExecuteDagState


class ErrorState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        if context.error_message:
            logger.error("DAG execution error: %s", context.error_message)
        for node in context.node_to_reference.values():
            # Cancel all nodes that haven't yet begun processing.
            if node.node_state == NodeState.QUEUED:
                node.node_state = NodeState.CANCELED
        # Shut down and cancel all threads/tasks that haven't yet ran. Currently running ones will not be affected.
        # Cancel async tasks
        for task in list(context.task_to_node.keys()):
            if not task.done():
                task.cancel()
        return ErrorState

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
        # Don't modify lists while iterating through them.
        task_to_node = context.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        # Handle async tasks
        task_to_node = context.task_to_node
        for task, node in task_to_node.copy().items():
            if task.done():
                node.node_state = NodeState.DONE
            elif task.cancelled():
                node.node_state = NodeState.CANCELED
            task_to_node.pop(task)

        if len(task_to_node) == 0:
            # Finish up. We failed.
            context.workflow_state = WorkflowState.ERRORED
            context.network.clear()
            context.node_to_reference.clear()
            context.task_to_node.clear()
            return DagCompleteState
        # Let's continue going through until everything is cancelled.
        return ErrorState


class DagCompleteState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class ParallelResolutionMachine(FSM[ParallelResolutionContext]):
    """State machine for building DAG structure without execution."""

    def __init__(
        self, flow_name: str, max_nodes_in_parallel: int | None = None, dag_builder: DagBuilder | None = None
    ) -> None:
        resolution_context = ParallelResolutionContext(
            flow_name, max_nodes_in_parallel=max_nodes_in_parallel, dag_builder=dag_builder
        )
        super().__init__(resolution_context)

    async def resolve_node(self, node: BaseNode | None = None) -> None:  # noqa: ARG002
        """Execute the DAG structure using the existing DagBuilder."""
        await self.start(ExecuteDagState)

    def change_debug_mode(self, *, debug_mode: bool) -> None:
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is DagCompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None
