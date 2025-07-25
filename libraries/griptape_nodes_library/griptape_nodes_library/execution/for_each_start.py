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
        self.add_parameter(self.exec_in)

        self.items_list = Parameter(
            name="items",
            tooltip="List of items to iterate through",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        # On Each Item control output - moved outside group for proper rendering
        self.exec_out = ControlParameterOutput(tooltip="Execute for each item in the list", name="exec_out")
        self.exec_out.ui_options = {"display_name": "On Each Item"}
        self.add_parameter(self.exec_out)

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

        # Explicit tethering to ForEachEnd node (hidden)
        self.loop = Parameter(
            name="loop",
            tooltip="Connected ForEach End Node",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.loop.ui_options = {"hide": True, "display_name": "Loop End Node"}
        self.add_parameter(self.loop)

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

        # Hidden control output - loop end condition
        self.loop_end_condition_met_signal = ControlParameterOutput(
            tooltip="Signal to ForEachEnd when loop should end", name="loop_end_condition_met_signal"
        )
        self.loop_end_condition_met_signal.ui_options = {"hide": True, "display_name": "Loop End Signal"}
        self.loop_end_condition_met_signal.settable = False

        # Add hidden parameters
        self.add_parameter(self.trigger_next_iteration_signal)
        self.add_parameter(self.break_loop_signal)
        self.add_parameter(self.loop_end_condition_met_signal)

        # Control output tracking
        self.next_control_output: Parameter | None = None
        self._logger = logging.getLogger(f"{__name__}.{self.name}")

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._flow is None:
            return

        # Handle different control entry points with direct logic
        match self._entry_control_parameter:
            case self.exec_in | None:
                # Starting the loop (initialization)
                self._initialize_loop()
                self._check_completion_and_set_output()
            case self.trigger_next_iteration_signal:
                # Next iteration signal from ForEach End - advance to next item
                self.current_index += 1
                self._check_completion_and_set_output()
            case self.break_loop_signal:
                # Break signal from ForEach End - halt loop immediately
                self._break_loop()
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
        # Return the control output determined by process()
        return self.next_control_output

    def _initialize_loop(self) -> None:
        """Initialize the loop with fresh parameter values."""
        # Reset all state for fresh loop execution
        self.current_index = 0
        self._items = []
        self.finished = False
        self.next_control_output = None

        # Reset the coupled ForEach End node's state for fresh loop runs
        if self.end_node and hasattr(self.end_node, "reset_for_workflow_run"):
            self.end_node.reset_for_workflow_run()  # type: ignore[attr-defined] (better damned well be a corresponding End Node type by this point)

        # Always initialize items list with fresh parameter value
        list_values = self.get_parameter_value("items")
        # Ensure the list is flattened
        if isinstance(list_values, list):
            self._items = [
                item for sublist in list_values for item in (sublist if isinstance(sublist, list) else [sublist])
            ]
        else:
            self._items = []

        # Unresolve future nodes immediately to ensure first iteration gets fresh values
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        connections.unresolve_future_nodes(self)

    def _check_completion_and_set_output(self) -> None:
        """Check if loop should end or continue and set appropriate control output."""
        # If empty list or finished all items, complete
        if not self._items or len(self._items) == 0 or self.current_index >= len(self._items):
            self.finished = True
            self.next_control_output = self.loop_end_condition_met_signal
            return

        # Continue with current item - unresolve future nodes for fresh evaluation
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        connections.unresolve_future_nodes(self)

        # Set current item data
        if self._items and self.current_index < len(self._items):
            current_item_value = self._items[self.current_index]
            self.parameter_output_values["current_item"] = current_item_value
            self.parameter_output_values["index"] = self.current_index
            self.publish_update_to_parameter("current_item", current_item_value)
            self.publish_update_to_parameter("index", self.current_index)

        # Continue with execution
        self.next_control_output = self.exec_out

    def _break_loop(self) -> None:
        """Break out of loop immediately."""
        self.finished = True
        self._items = []
        self.current_index = 0
        self.next_control_output = self.loop_end_condition_met_signal

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

        # Check if loop has outgoing connection to ForEach End
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

            # Note: outgoing connections (loop_end_condition_met_signal) are tracked via end_node relationship

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
        if source_parameter == self.loop and isinstance(target_node, EndLoopNode):
            self.end_node = target_node
        return super().after_outgoing_connection(source_parameter, target_node, target_parameter)

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        if source_parameter == self.loop and isinstance(target_node, EndLoopNode):
            self.end_node = None
        return super().after_outgoing_connection_removed(source_parameter, target_node, target_parameter)
