from __future__ import annotations

import logging
import time
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor

from griptape.utils import with_contextvars

from griptape_nodes.app.app_sessions import event_queue
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState, ParameterTypeBuiltin
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.data_helpers import (
    clear_parameter_output_values,
    get_library_name,
    pass_values_to_connected_nodes,
)
from griptape_nodes.machines.execution_utils import CompleteState, Focus, ResolutionContext
from griptape_nodes.machines.fsm import State
from griptape_nodes.machines.ui_helpers import (
    log_serialization,
    mark_node_as_finished,
    mark_node_as_starting,
)
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    NodeFinishProcessEvent,
    NodeResolvedEvent,
    ParameterValueUpdateEvent,
)

logger = logging.getLogger("griptape_nodes")


class ExecuteNodeState(State):
    """State responsible for executing ready nodes in the flow graph.

    The state repeatedly performs the following steps until all work is
    finished:

    1. Discover nodes that are ready to run via ResolutionContext.DAG.
    2. Spin up a Focus object for each newly ready node and push it on
       to ResolutionContext.current_focuses.
    3. Drive each focus forward by invoking the corresponding node process
       method through do_ui_tasks_and_run_node.
    4. Mark nodes as processed/resolved and transition to CompleteState once the
       DAG is empty.
    """

    executor: ThreadPoolExecutor = ThreadPoolExecutor()

    @staticmethod
    def on_enter(_: ResolutionContext) -> type[State] | None:
        """Return the starting state for the FSM."""
        return ExecuteNodeState

    @staticmethod
    def on_update(context: ResolutionContext) -> type[State] | None:
        """Main execution loop."""
        ready_nodes = context.DAG.get_ready_nodes()
        # Prepare a list of current focuses
        for node in ready_nodes:
            # if it is not already in the current focuses
            if node not in [focus.node for focus in context.current_focuses]:
                ExecuteNodeState._before_node(node)
                focus_obj = Focus(node, scheduled_value=None, process_generator=None)
                context.current_focuses.append(focus_obj)

        for focus in context.current_focuses.copy():
            # if we are calling it for the first time or there is an update in the scheduled value, run it
            done = False
            if focus.updated:
                try:
                    # This returns False if the node is not done
                    done = ExecuteNodeState.do_ui_tasks_and_run_node(focus)
                except Exception as exc:
                    msg = f"Node execution failed for node {focus.node.name} because of {exc}"
                    raise RuntimeError(msg) from exc
                focus.updated = False
            # If the node is done
            if done:
                context.DAG.mark_processed(focus.node)
                context.current_focuses.remove(focus)

        # If we don't have any more nodes left, we are done
        if context.DAG.get_all_nodes() == []:
            return CompleteState

        # Wait for a bit before checking again
        time.sleep(0.1)
        return ExecuteNodeState

    @staticmethod
    def do_ui_tasks_and_run_node(current_focus: Focus) -> bool:
        """Execute a node and perform related UI/event bookkeeping.

        Args:
            current_focus: The Focus object wrapping the current node.

        Returns:
            True if the node has scheduled asynchronous work and therefore
            still needs further processing, otherwise False signaling that
            the node has completely finished.
        """
        current_node = current_focus.node
        mark_node_as_starting(current_focus)

        try:
            more_work = ExecuteNodeState._run_node_process_method(current_focus)
            # If the node is still not done
            if more_work:
                logger.debug("Pausing Node '%s' to run background work", current_node.name)
                return False
        except Exception as exc:
            logger.exception("Error processing node '%s'", current_node.name)
            msg = f"Canceling flow run. Node '{current_node.name}' encountered a problem: {exc}"
            # Mark the node as unresolved, broadcasting to everyone.
            current_node.make_node_unresolved(
                current_states_to_trigger_change_event=set(
                    {NodeResolutionState.UNRESOLVED, NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                )
            )

            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            GriptapeNodes.FlowManager().cancel_flow_run()

            event_queue.put(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeFinishProcessEvent(node_name=current_node.name))
                )
            )
            raise RuntimeError(msg) from exc

        # Various tasks done by helper class
        mark_node_as_finished(current_focus)
        log_serialization(current_focus)
        pass_values_to_connected_nodes(current_focus)

        return True

    @staticmethod
    def _before_node(current_node: BaseNode) -> None:
        """Prepare a node for execution by clearing/propagating parameter values and performing validation.

        This method is called immediately before a node's ``process`` method is
        first invoked.  It ensures that all parameter values are up-to-date and
        publishes their values to the UI.  Validation errors raised here
        propagate up and abort the flow run early.
        """
        # Clear all of the current output values
        clear_parameter_output_values(current_node)
        # Iterate over all parameters of the current node
        for parameter in current_node.parameters:
            # Skip parameters that are of control type (not data parameters)
            if ParameterTypeBuiltin.CONTROL_TYPE.value.lower() == parameter.output_type:
                continue
            # If the parameter value is not already set
            if parameter.name not in current_node.parameter_values:
                # Try to get the parameter's value (could be from a default or connection)
                value = current_node.get_parameter_value(parameter.name)
                if value is not None:
                    # If a value is found, set it in the node's parameter values
                    current_node.set_parameter_value(parameter.name, value)

            # If the parameter value is now set (either previously or just above)
            if parameter.name in current_node.parameter_values:
                parameter_value = current_node.get_parameter_value(parameter.name)
                data_type = parameter.type
                if data_type is None:
                    data_type = ParameterTypeBuiltin.NONE.value
                # Publish an event to update the UI/system with the parameter's value
                event_queue.put(
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

    @staticmethod
    def _run_node_process_method(current_focus: Focus) -> bool:
        """Run the process method of the node.

        If the node's process method returns a generator, take the next value from the generator (a callable) and run
        that in a thread pool executor. The result of that callable will be passed to the generator when it is resumed.

        This has the effect of pausing at a yield expression, running the expression in a thread, and resuming when the thread pool is done.

        Args:
            current_focus (Focus): The current focus.

        Returns:
            bool: True if work has been scheduled, False if the node is done processing.
        """

        def on_future_done(future: Future) -> None:
            """Called when the future is done.

            Stores the result of the future in the node's context, and publishes an event to resume the flow.
            """
            current_focus.updated = True
            try:
                current_focus.scheduled_value = future.result()
            except Exception as e:
                logger.info("Error in future: %s", e)
                current_focus.scheduled_value = e

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
