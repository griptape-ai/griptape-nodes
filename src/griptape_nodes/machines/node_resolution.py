from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from sqlite3 import connect
from this import d
from typing import Any
from collections import defaultdict
from griptape.events import EventBus
from griptape.utils import with_contextvars

from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin, Parameter
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
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    NodeStartProcessEvent,
    ParameterSpotlightEvent,
    ParameterValueUpdateEvent,
    ResumeNodeProcessingEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    SetParameterValueRequest,
)

logger = logging.getLogger("griptape_nodes")

# Directed Acyclic Graph
class DAG:
    def __init__(self):
        self.graph = defaultdict(set)        # adjacency list
        self.in_degree = defaultdict(int)    # number of unmet dependencies

    def add_node(self, node):
        self.graph[node]  # ensures node exists

    def add_edge(self, from_node, to_node):
        self.graph[from_node].add(to_node)
        self.in_degree[to_node] += 1

    def get_ready_nodes(self):
        return [node for node in self.graph if self.in_degree[node] == 0]

    def mark_processed(self, node):
        for neighbor in self.graph[node]:
            self.in_degree[neighbor] -= 1
        self.in_degree[node] = -1  # Mark as done

@dataclass
class Focus:
    node: BaseNode
    scheduled_value: Any | None = None
    process_generator: Generator | None = None


# This is on a per-node basis
class ResolutionContext:
    root_node_resolving: BaseNode | None
    paused: bool
    DAG: DAG

    def __init__(self) -> None:
        self.root_node_resolving = None
        self.DAG = DAG()
        self.paused = False

    def reset(self) -> None:
        # If a DAG exists, clear all nodes in the DAG
        if self.DAG is not None:
            for node in self.DAG.graph:
                node.clear_node()
            self.DAG.graph.clear()
            self.DAG.in_degree.clear()
        self.paused = False


class EvaluateParameterState(State):
    @staticmethod

    def initialize_spotlight(current_node):
        if current_node.state == NodeResolutionState.UNRESOLVED:
            """Mark all future nodes unresolved and initialize spotlight"""
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.FlowManager().get_connections().unresolve_future_nodes(current_node)
            current_node.initialize_spotlight()

    def add_dependencies_to_graph(self, current_node: BaseNode, context: ResolutionContext):
        self.initialize_spotlight(current_node)
        while current_node.current_spotlight_parameter is not None:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            connections = GriptapeNodes.FlowManager().get_connections()

            connected_node_and_parameter: tuple[BaseNode, Parameter] | None = connections.get_connected_node(current_node, current_node.current_spotlight_parameter)
            if connected_node_and_parameter is None:
                # Guess the connected node didn't exist, so continuing the loop
                continue
            (connected_node, _) = connected_node_and_parameter
            if connected_node in context.DAG.graph.keys():
                raise RuntimeError(f"Cycle detected between node {current_node.name} and {connected_node.name}")
            # Update DAG
            context.DAG.add_node(connected_node)
            context.DAG.add_edge(connected_node, current_node)
            # Recursion
            self.add_dependencies_to_graph(connected_node, context)
            current_node.advance_parameter()

    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        pass

    def on_update(self, context: ResolutionContext) -> type[State] | None:
        if isinstance(context.root_node_resolving, BaseNode):
            self.add_dependencies_to_graph(context.root_node_resolving, context)
        print("all nodes")
        for node in context.DAG.graph.keys():
            print(node.name)
        print("get ready nodes")
        for node in context.DAG.get_ready_nodes():
            print(node.name)
        return CompleteState

"""
class ExecuteNodeState(State):
    executor: ThreadPoolExecutor = ThreadPoolExecutor()

    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/864
    @staticmethod
    def clear_parameter_output_values(context: ResolutionContext) -> None:
        Clears all parameter output values for the currently focused node in the resolution context.

        This method iterates through each parameter output value stored in the current node,
        removes it from the node's parameter_output_values dictionary, and publishes an event
        to notify the system about the parameter value being set to None.

        Args:
            context (ResolutionContext): The resolution context containing the focus stack
                with the current node being processed.

        Raises:
            ValueError: If a parameter name in parameter_output_values doesn't correspond
                to an actual parameter in the node.

        Note:
            - Uses a copy of parameter_output_values to safely modify the dictionary during iteration
            - For each parameter, publishes a ParameterValueUpdateEvent with value=None
            - Events are wrapped in ExecutionGriptapeNodeEvent before publishing
        current_node = context.focus_stack[-1].node
        for parameter_name in current_node.parameter_output_values.copy():
            parameter = current_node.get_parameter_by_name(parameter_name)
            if parameter is None:
                err = f"Attempted to execute node '{current_node.name}' but could not find parameter '{parameter_name}' that was indicated as having a value."
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
            EventBus.publish_event(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
        current_node.parameter_output_values.clear()

    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:
        current_node = context.focus_stack[-1].node
        # Clear all of the current output values
        ExecuteNodeState.clear_parameter_output_values(context)
        for parameter in current_node.parameters:
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue
            if parameter.name not in current_node.parameter_values:
                # If a parameter value is not already set
                value = current_node.get_parameter_value(parameter.name)
                if value is not None:
                    current_node.set_parameter_value(parameter.name, value)

            if parameter.name in current_node.parameter_values:
                parameter_value = current_node.get_parameter_value(parameter.name)
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                EventBus.publish_event(
                    ExecutionGriptapeNodeEvent(
                        wrapped_event=ExecutionEvent(
                            payload=ParameterValueUpdateEvent(
                                node_name=current_node.name,
                                parameter_name=parameter.name,
                                # this is because the type is currently IN the parameter.
                                data_type=data_type,
                                value=TypeValidator.safe_serialize(parameter_value),
                            )
                        )
                    )
                )

        exceptions = current_node.validate_before_node_run()
        if exceptions:
            msg = f"Canceling flow run. Node '{current_node.name}' encountered problems: {exceptions}"
            # Mark the node as unresolved, broadcasting to everyone.
            raise RuntimeError(msg)
        if not context.paused:
            return ExecuteNodeState
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Once everything has been set
        current_focus = context.focus_stack[-1]
        current_node = current_focus.node
        # To set the event manager without circular import errors
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeStartProcessEvent(node_name=current_node.name))
            )
        )
        logger.info("Node '%s' is processing.", current_node.name)

        try:
            work_is_scheduled = ExecuteNodeState._process_node(current_focus)
            if work_is_scheduled:
                logger.debug("Pausing Node '%s' to run background work", current_node.name)
                return None
        except Exception as e:
            logger.exception("Error processing node '%s", current_node.name)
            msg = f"Canceling flow run. Node '{current_node.name}' encountered a problem: {e}"
            # Mark the node as unresolved, broadcasting to everyone.
            current_node.make_node_unresolved(
                current_states_to_trigger_change_event=set(
                    {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                )
            )
            current_focus.process_generator = None
            current_focus.scheduled_value = None

            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.FlowManager().cancel_flow_run()

            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                )
            )
            raise RuntimeError(msg) from e

        logger.info("Node '%s' finished processing.", current_node.name)

        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
            )
        )
        current_node.state = NodeResolutionState.RESOLVED
        details = f"'{current_node.name}' resolved."

        logger.info(details)

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
            EventBus.publish_event(
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
            # Pass the value through to the new nodes.
            conn_output_nodes = GriptapeNodes.FlowManager().get_connected_output_parameters(current_node, parameter)
            for target_node, target_parameter in conn_output_nodes:
                GriptapeNodes.get_instance().handle_request(
                    SetParameterValueRequest(
                        parameter_name=target_parameter.name,
                        node_name=target_node.name,
                        value=value,
                        data_type=parameter.output_type,
                    )
                )

        # Output values should already be saved!
        library = LibraryRegistry.get_libraries_with_node_type(current_node.__class__.__name__)
        if len(library) == 1:
            library_name = library[0]
        else:
            library_name = None
        EventBus.publish_event(
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
        context.focus_stack.pop()
        if len(context.focus_stack):
            return EvaluateParameterState

        return CompleteState

    @staticmethod
    def _process_node(current_focus: Focus) -> bool:
        Run the process method of the node.

        If the node's process method returns a generator, take the next value from the generator (a callable) and run
        that in a thread pool executor. The result of that callable will be passed to the generator when it is resumed.

        This has the effect of pausing at a yield expression, running the expression in a thread, and resuming when the thread pool is done.

        Args:
            current_focus (Focus): The current focus.

        Returns:
            bool: True if work has been scheduled, False if the node is done processing.

        def on_future_done(future: Future) -> None:
            alled when the future is done.

            Stores the result of the future in the node's context, and publishes an event to resume the flow.

            try:
                current_focus.scheduled_value = future.result()
            except Exception as e:
                logger.debug("Error in future: %s", e)
                current_focus.scheduled_value = e
            finally:
                # If it hasn't been cancelled.
                if current_focus.process_generator:
                    EventBus.publish_event(
                        ExecutionGriptapeNodeEvent(
                            wrapped_event=ExecutionEvent(payload=ResumeNodeProcessingEvent(node_name=current_node.name))
                        )
                    )

        current_node = current_focus.node
        # Only start the processing if we don't already have a generator
        logger.debug("Node '%s' process generator: %s", current_node.name, current_focus.process_generator)
        if current_focus.process_generator is None:
            result = current_node.process()

            # If the process returned a generator, we need to store it for later
            if isinstance(result, Generator):
                current_focus.process_generator = result
                logger.debug("Node '%s' returned a generator.", current_node.name)

        # We now have a generator, so we need to run it
        if current_focus.process_generator is not None:
            try:
                logger.debug(
                    "Node '%s' has an active generator, sending scheduled value of type: %s",
                    current_node.name,
                    type(current_focus.scheduled_value),
                )
                if isinstance(current_focus.scheduled_value, Exception):
                    func = current_focus.process_generator.throw(current_focus.scheduled_value)
                else:
                    func = current_focus.process_generator.send(current_focus.scheduled_value)

                # Once we've passed on the scheduled value, we should clear it out just in case
                current_focus.scheduled_value = None

                future = ExecuteNodeState.executor.submit(with_contextvars(func))
                future.add_done_callback(with_contextvars(on_future_done))
            except StopIteration:
                logger.debug("Node '%s' generator is done.", current_node.name)
                # If that was the last generator, clear out the generator and indicate that there is no more work scheduled
                current_focus.process_generator = None
                current_focus.scheduled_value = None
                return False
            else:
                # If the generator is not done, indicate that there is work scheduled
                logger.debug("Node '%s' generator is not done.", current_node.name)
                return True
        logger.debug("Node '%s' did not return a generator.", current_node.name)
        return False
"""

class CompleteState(State):
    @staticmethod
    def on_enter(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:  # noqa: ARG004
        return None

class NodeResolutionMachine(FSM[ResolutionContext]):
    """State machine for resolving node dependencies."""

    def __init__(self) -> None:
        resolution_context = ResolutionContext()
        super().__init__(resolution_context)

    def resolve_node(self, node: BaseNode) -> None:
        self._context.root_node_resolving = node
        self.start(EvaluateParameterState)

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode

    def is_complete(self) -> bool:
        return self._current_state is CompleteState

    def is_started(self) -> bool:
        return self._current_state is not None

    def reset_machine(self) -> None:
        self._context.reset()
        self._current_state = None
