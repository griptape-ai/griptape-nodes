import logging
from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode, StartLoopNode
from griptape_nodes.machines.fsm import FSM, State


class WaitingForStartState(State):
    """Initial state - initializes items list and transitions to check end condition."""

    @staticmethod
    def on_enter(context: "ForEachStartNode") -> type[State] | None:
        """Initialize the items list on entry."""
        # Always initialize items list with fresh parameter value
        list_values = context.get_parameter_value("items")
        # Ensure the list is flattened
        if isinstance(list_values, list):
            context._items = [
                item for sublist in list_values for item in (sublist if isinstance(sublist, list) else [sublist])
            ]
        else:
            context._items = []

        # Unresolve future nodes immediately to ensure first iteration gets fresh values
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        connections.unresolve_future_nodes(context)

        return None

    @staticmethod
    def on_update(context: "ForEachStartNode") -> type[State] | None:  # noqa: ARG004
        """Always transition to check end condition after initialization."""
        # Always transition to check end condition - we're past initialization
        return CheckEndConditionMetState

    @staticmethod
    def on_event(context: "ForEachStartNode", event: Any) -> type[State] | None:
        """Handle initial exec_in event."""
        if event == context.exec_in:
            # Force transition to check end condition when exec_in is received
            return CheckEndConditionMetState
        return None


class CheckEndConditionMetState(State):
    """State that checks if loop should end or continue."""

    @staticmethod
    def on_enter(context: "ForEachStartNode") -> type[State] | None:
        """Check if we should continue or end the loop and set appropriate output."""
        # If empty list or finished all items, complete
        if not context._items or len(context._items) == 0 or context.current_index >= len(context._items):
            context.finished = True
            context.next_control_output = context.loop_end_condition_met_signal
            return CompletedState

        # Unresolve future nodes before continuing to ensure fresh parameter evaluation
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        connections.unresolve_future_nodes(context)

        # Continue with current item
        context.next_control_output = context.exec_out
        return ExecuteCurrentItemState

    @staticmethod
    def on_update(context: "ForEachStartNode") -> type[State] | None:  # noqa: ARG004
        """Should not stay in this state - always transition in on_enter."""
        return None

    @staticmethod
    def on_event(context: "ForEachStartNode", event: Any) -> type[State] | None:  # noqa: ARG004
        """No events handled in this state."""
        return None


class ExecuteCurrentItemState(State):
    """State for executing current item - sets data in on_enter and handles events."""

    @staticmethod
    def on_enter(context: "ForEachStartNode") -> type[State] | None:
        """Set current item data immediately on entering this state."""
        # Set current item data if we have items
        if context._items and context.current_index < len(context._items):
            current_item_value = context._items[context.current_index]
            context.parameter_output_values["current_item"] = current_item_value
            context.parameter_output_values["index"] = context.current_index
            context.publish_update_to_parameter("current_item", current_item_value)
            context.publish_update_to_parameter("index", context.current_index)

        # Don't set next_control_output here - let it keep what CheckEndConditionMetState set
        return None

    @staticmethod
    def on_update(context: "ForEachStartNode") -> type[State] | None:  # noqa: ARG004
        """Stay in execution state until event received."""
        return None

    @staticmethod
    def on_event(context: "ForEachStartNode", event: Any) -> type[State] | None:
        """Handle next iteration or break signals."""
        if event == context.trigger_next_iteration_signal:
            # Advance to next item
            context.current_index += 1
            # Transition to check end condition
            return CheckEndConditionMetState

        if event == context.break_loop_signal:
            # Break out of loop
            context.finished = True
            context._items = []
            context.current_index = 0
            context.next_control_output = context.loop_end_condition_met_signal
            return CompletedState

        return None


class CompletedState(State):
    """Final state when loop is completed."""

    @staticmethod
    def on_enter(context: "ForEachStartNode") -> type[State] | None:
        """Loop is completed - set completion signal immediately."""
        context.next_control_output = context.loop_end_condition_met_signal
        return None

    @staticmethod
    def on_update(context: "ForEachStartNode") -> type[State] | None:  # noqa: ARG004
        """Stay in completed state."""
        return None

    @staticmethod
    def on_event(context: "ForEachStartNode", event: Any) -> type[State] | None:  # noqa: ARG004
        """No events handled in completed state."""
        return None


class ForEachStartNode(StartLoopNode):
    """For Each Start Node that runs a connected flow for each item in a parameter list.

    This node iterates through each item in the input list and runs the connected flow for each item.
    It provides the current item to the next node in the flow and keeps track of the iteration state.
    """

    _items: list[Any] | None = None
    _flow: ControlFlow | None = None

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.finished = False
        self.current_index = 0
        self._items = None

        # Debug: We'll override set_parameter_value in a method below

        # Connection tracking for validation
        self._connected_parameters: set[str] = set()
        # Main control flow
        self.exec_in = ControlParameterInput(tooltip="Start Loop", name="exec_in")
        self.exec_in.ui_options = {"display_name": "Start Loop"}
        self.exec_out = ControlParameterOutput(tooltip="Execute for each item in the list", name="exec_out")
        self.exec_out.ui_options = {"display_name": "On Each Item"}
        self.add_parameter(self.exec_in)
        self.add_parameter(self.exec_out)
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to iterate through",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        with ParameterGroup(name="For Each Item") as group:
            # Add current item output parameter
            self.current_item = Parameter(
                name="current_item",
                tooltip="Current item being processed",
                output_type=ParameterTypeBuiltin.ALL.value,
                allowed_modes={ParameterMode.OUTPUT},
                settable=False,
            )
            self.index_count = Parameter(
                name="index",
                tooltip="Current index of the iteration",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                settable=False,
                default_value=0,
                ui_options={"hide_property": True},
            )
        self.add_node_element(group)

        # Explicit tethering to ForEachEnd node
        self.loop_end_node = Parameter(
            name="loop_end_node",
            tooltip="Connected ForEach End Node",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.loop_end_node.ui_options = {"display_name": "Loop End Node"}
        self.add_parameter(self.loop_end_node)

        # Hidden signal inputs from ForEachEnd
        self.trigger_next_iteration_signal = ControlParameterInput(
            tooltip="Signal from ForEachEnd to continue to next iteration", name="trigger_next_iteration_signal"
        )
        self.trigger_next_iteration_signal.ui_options = {"hide": True, "display_name": "Next Iteration Signal"}
        self.trigger_next_iteration_signal.settable = False

        self.break_loop_signal = ControlParameterInput(
            tooltip="Signal from ForEachEnd to break out of loop", name="break_loop_signal"
        )
        self.break_loop_signal.ui_options = {"hide": True, "display_name": "Break Loop Signal"}
        self.break_loop_signal.settable = False

        # Hidden data output - results list
        self.results_list = Parameter(
            name="results_list",
            tooltip="Results list passed to ForEach End Node",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=[],
        )
        self.results_list.ui_options = {"hide": True}

        # Hidden control output - loop end condition
        self.loop_end_condition_met_signal = ControlParameterOutput(
            tooltip="Signal to ForEachEnd when loop should end", name="loop_end_condition_met_signal"
        )
        self.loop_end_condition_met_signal.ui_options = {"hide": True, "display_name": "Loop End Signal"}
        self.loop_end_condition_met_signal.settable = False

        # Add hidden parameters
        self.add_parameter(self.trigger_next_iteration_signal)
        self.add_parameter(self.break_loop_signal)
        self.add_parameter(self.results_list)
        self.add_parameter(self.loop_end_condition_met_signal)

        # Initialize FSM and control output tracking
        self._fsm = FSM(self)
        self.next_control_output: Parameter | None = None
        self._logger = logging.getLogger(f"{__name__}.{self.name}")

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._flow is None or self.finished:
            return

        # Handle different control entry points
        match self._entry_control_parameter:
            case self.exec_in | None:
                # Starting the loop (either via connection or direct execution)
                # Initialize FSM to WaitingForStartState to get fresh parameter values
                self._fsm.start(WaitingForStartState)
                self._fsm.update()
            case self.trigger_next_iteration_signal:
                # Next iteration signal from ForEach End - advance to next item
                self.current_index += 1
                # Transition to check if we should continue or end
                self._fsm.transition_state(CheckEndConditionMetState)
            case self.break_loop_signal:
                # Break signal from ForEach End - halt loop immediately
                self.finished = True
                self._items = []
                self.current_index = 0
                self._fsm.transition_state(CompletedState)
            case _:
                # Unexpected control entry point - log error for debugging
                err_str = f"ForEach Start node '{self.name}' received unexpected control parameter: {self._entry_control_parameter}. "
                "Expected: exec_in, trigger_next_iteration_signal, break_loop_signal, or None."

                self._logger.error(err_str)
                return

    # This node cannot run unless it's connected to a start node.
    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        # Force complete reset of all state
        self.current_index = 0
        self._items = []
        self.finished = False
        self.next_control_output = None

        # Clear the coupled ForEach End node's state for fresh workflow runs
        from griptape_nodes_library.execution.for_each_end import ForEachEndNode

        if isinstance(self.end_node, ForEachEndNode):
            self.end_node.reset_for_workflow_run()

        # Validate end node connection
        if self.end_node is None:
            msg = f"{self.name}: End node not found or connected."
            exceptions.append(Exception(msg))

        # Validate all required connections exist
        validation_errors = self._validate_foreach_connections()
        if validation_errors:
            exceptions.extend(validation_errors)

        try:
            flow = GriptapeNodes.ObjectManager().get_object_by_name(
                GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
            )
            if isinstance(flow, ControlFlow):
                self._flow = flow
        except Exception as e:
            exceptions.append(e)
        return exceptions

    # This node cannot be run unless it's connected to an end node.
    def validate_before_node_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        if self.end_node is None:
            msg = f"{self.name}: End node not found or connected."
            exceptions.append(Exception(msg))

        # Validate all required connections exist
        validation_errors = self._validate_foreach_connections()
        if validation_errors:
            exceptions.extend(validation_errors)

        try:
            flow = GriptapeNodes.ObjectManager().get_object_by_name(
                GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
            )
            if isinstance(flow, ControlFlow):
                self._flow = flow
        except Exception as e:
            exceptions.append(e)
        return exceptions

    def get_next_control_output(self) -> Parameter | None:
        # Return what the FSM state set as the next control output
        # Note: Events are already handled in process(), no need to handle again
        return self.next_control_output

    def _validate_foreach_connections(self) -> list[Exception]:
        """Validate that all required ForEach connections are properly established.

        Returns a list of validation errors with detailed instructions for the user.
        """
        errors = []

        # Check if items parameter has input connection
        if "items" not in self._connected_parameters:
            errors.append(
                Exception(
                    f"{self.name}: Missing required 'items' connection. "
                    "REQUIRED ACTION: Connect a data source (like Create List.output) to the ForEach Start 'items' input. "
                    "The ForEach Start needs a list of items to iterate through."
                )
            )

        # Check if loop_end_node has outgoing connection to ForEach End
        if self.end_node is None:
            errors.append(
                Exception(
                    f"{self.name}: Missing required tethering connection. "
                    "REQUIRED ACTION: Connect ForEach Start 'Loop End Node' to ForEach End 'Loop Start Node'. "
                    "This establishes the explicit relationship between start and end nodes."
                )
            )

        # Check if all hidden signal connections exist (only if end_node is connected)
        if self.end_node:
            # Check signal inputs from ForEach End
            if "trigger_next_iteration_signal" not in self._connected_parameters:
                errors.append(
                    Exception(
                        f"{self.name}: Missing hidden signal connection. "
                        "REQUIRED ACTION: Connect ForEach End 'Next Iteration Signal Output' to ForEach Start 'Next Iteration Signal'. "
                        "This signal tells the start node to continue to the next item."
                    )
                )

            if "break_loop_signal" not in self._connected_parameters:
                errors.append(
                    Exception(
                        f"{self.name}: Missing hidden signal connection. "
                        "REQUIRED ACTION: Connect ForEach End 'Break Loop Signal Output' to ForEach Start 'Break Loop Signal'. "
                        "This signal tells the start node to break out of the loop early."
                    )
                )

            # Note: outgoing connections (results_list, loop_end_condition_met_signal) are tracked via end_node relationship

        return errors

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Track incoming connections for validation
        self._connected_parameters.add(target_parameter.name)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Remove from tracking when connection is removed
        self._connected_parameters.discard(target_parameter.name)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        if source_parameter == self.loop_end_node and isinstance(target_node, EndLoopNode):
            self.end_node = target_node
        return super().after_outgoing_connection(source_parameter, target_node, target_parameter)

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        if source_parameter == self.loop_end_node and isinstance(target_node, EndLoopNode):
            self.end_node = None
        return super().after_outgoing_connection_removed(source_parameter, target_node, target_parameter)
