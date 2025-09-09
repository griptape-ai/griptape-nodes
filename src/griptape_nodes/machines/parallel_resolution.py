from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from griptape_nodes.common.directed_graph import DirectedGraph
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    CurrentDataNodeEvent,
    NodeResolvedEvent,
    ParameterSpotlightEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest

logger = logging.getLogger("griptape_nodes")


class NodeState(StrEnum):
    """Individual node execution states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    ERRORED = "errored"
    WAITING = "waiting"


@dataclass(kw_only=True)
class DagNode:
    """Represents a node in the DAG with runtime references."""

    task_reference: asyncio.Task | None = field(default=None)
    node_state: NodeState = field(default=NodeState.WAITING)
    node_reference: BaseNode


@dataclass
class Focus:
    node: BaseNode
    scheduled_value: Any | None = None


class WorkflowState(StrEnum):
    """Workflow execution states."""

    NO_ERROR = "no_error"
    WORKFLOW_COMPLETE = "workflow_complete"
    ERRORED = "errored"
    CANCELED = "canceled"


class ParallelResolutionContext:
    focus_stack: list[Focus]
    paused: bool
    flow_name: str
    build_only: bool
    batched_nodes: list[BaseNode]
    error_message: str | None
    workflow_state: WorkflowState
    # DAG fields moved from DagOrchestrator
    network: DirectedGraph
    node_to_reference: dict[str, DagNode]
    async_semaphore: asyncio.Semaphore
    task_to_node: dict[asyncio.Task, DagNode]

    def __init__(self, flow_name: str, max_nodes_in_parallel: int | None = None) -> None:
        self.flow_name = flow_name
        self.focus_stack = []
        self.paused = False
        self.build_only = False
        self.batched_nodes = []
        self.error_message = None
        self.workflow_state = WorkflowState.NO_ERROR

        # Initialize DAG fields
        self.network = DirectedGraph()
        self.node_to_reference = {}
        max_nodes_in_parallel = max_nodes_in_parallel if max_nodes_in_parallel is not None else 5
        self.async_semaphore = asyncio.Semaphore(max_nodes_in_parallel)
        self.task_to_node = {}

    def reset(self, *, cancel: bool = False) -> None:
        if self.focus_stack:
            node = self.focus_stack[-1].node
            node.clear_node()
        self.focus_stack.clear()
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


class InitializeDagSpotlightState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
        if not len(context.focus_stack):
            return DagCompleteState
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        current_parameter = current_node.get_current_parameter()
        if current_parameter is None:
            return BuildDagNodeState
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
            if next_node.state == NodeResolutionState.UNRESOLVED:
                focus_stack_names = {focus.node.name for focus in context.focus_stack}
                if next_node.name in focus_stack_names:
                    msg = f"Cycle detected between node '{current_node.name}' and '{next_node.name}'."
                    raise RuntimeError(msg)
                context.network.add_edge(next_node.name, current_node.name)
                context.focus_stack.append(Focus(node=next_node))
                return InitializeDagSpotlightState
            if next_node.state == NodeResolutionState.RESOLVED and next_node in context.batched_nodes:
                context.network.add_edge(next_node.name, current_node.name)
        if current_node.advance_parameter():
            return InitializeDagSpotlightState
        return BuildDagNodeState


class BuildDagNodeState(State):
    @staticmethod
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node

        # Add the current node to the DAG
        node_reference = DagNode(node_reference=current_node)
        context.node_to_reference[current_node.name] = node_reference
        # Add node name to DAG (has to be a hashable value)
        context.network.add_node(node_for_adding=current_node.name)

        if not context.paused:
            return BuildDagNodeState
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
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
    def handle_done_nodes(done_node: DagNode) -> None:
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
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

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
    def collect_values_from_upstream_nodes(node_reference: DagNode) -> None:
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
                        incoming_connection_source_node_name=upstream_node.name,
                        incoming_connection_source_parameter_name=upstream_parameter.name,
                    )
                )

    @staticmethod
    def clear_parameter_output_values(node_reference: DagNode) -> None:
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
        for parameter_name in current_node.parameter_output_values:
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
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.EventManager().put_event(
                ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload))
            )
        current_node.parameter_output_values.clear()

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
        context.batched_nodes.clear()
        for node in context.node_to_reference.values():
            # We have a DAG. Flag all nodes in DAG as queued. Workflow state is NO_ERROR
            node.node_state = NodeState.QUEUED
        context.workflow_state = WorkflowState.NO_ERROR
        if not context.paused:
            return ExecuteDagState
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:
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
            ExecuteDagState.handle_done_nodes(context.node_to_reference[node])
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
                ExecuteDagState.collect_values_from_upstream_nodes(node_reference)
            except Exception as e:
                logger.exception("Error collecting parameter values for node '%s'", node_reference.node_reference.name)
                context.error_message = (
                    f"Parameter passthrough failed for node '{node_reference.node_reference.name}': {e}"
                )
                context.workflow_state = WorkflowState.ERRORED
                return ErrorState

            # Clear parameter output values before execution
            try:
                ExecuteDagState.clear_parameter_output_values(node_reference)
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
                node = context.task_to_node.pop(task)
                node.node_state = NodeState.DONE
                logger.info("Task done: %s", node.node_reference.name)

            # Execute the node asynchronously
            node_task = asyncio.create_task(ExecuteDagState.execute_node(node_reference, context.async_semaphore))
            # Add a callback to set node to done when task has finished.
            context.task_to_node[node_task] = node_reference
            node_reference.task_reference = node_task
            node_task.add_done_callback(lambda t: on_task_done(t))
            node_reference.node_state = NodeState.PROCESSING
            node_reference.node_reference.state = NodeResolutionState.RESOLVING
            # Wait for a task to finish
        await asyncio.wait(context.task_to_node.keys(), return_when=asyncio.FIRST_COMPLETED)
        # Once a task has finished, loop back to the top.
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
    async def on_enter(context: ParallelResolutionContext) -> type[State] | None:
        # Set build_only back to False.
        context.build_only = False
        return None

    @staticmethod
    async def on_update(context: ParallelResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None


class ParallelResolutionMachine(FSM[ParallelResolutionContext]):
    """State machine for building DAG structure without execution."""

    def __init__(self, flow_name: str, max_nodes_in_parallel: int | None = None) -> None:
        resolution_context = ParallelResolutionContext(flow_name, max_nodes_in_parallel=max_nodes_in_parallel)
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

    def reset_machine(self, *, cancel: bool = False) -> None:
        self._context.reset(cancel=cancel)
        self._current_state = None
