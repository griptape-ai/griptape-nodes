from typing import Any, Optional, override

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, StartLoopNode


class ForEachStartNode(StartLoopNode):
    """For Each Start Node that runs a connected flow for each item in a parameter list.

    This node iterates through each item in the input list and runs the connected flow for each item.
    It provides the current item to the next node in the flow and keeps track of the iteration state.
    """

    flow: ControlFlow

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add control output parameter for the loop body
        self.loop_body = ControlParameterOutput(
            tooltip="Loop body - executed for each item in the list", name="loop_body"
        )
        self.loop_body.ui_options = {"display_name": "Loop Body"}
        self.add_parameter(self.loop_body)

        # Add control output parameter after the loop completes
        self.completed = ControlParameterOutput(
            tooltip="Executed after all items have been processed", name="completed"
        )
        self.completed.ui_options = {"display_name": "Completed"}
        self.add_parameter(self.completed)

        # Add parameter list for input items
        self.items_list = ParameterList(
            name="items",
            tooltip="List of items to iterate through",
            input_types=[ParameterTypeBuiltin.ALL.value],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        # Add current item output parameter
        self.current_item = Parameter(
            name="current_item",
            tooltip="Current item being processed",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.current_item)

        # Add index output parameter
        self.index = Parameter(
            name="index",
            tooltip="Current index in the iteration",
            output_type="int",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=0,
        )
        self.add_parameter(self.index)

        # Add count output parameter
        self.count = Parameter(
            name="count",
            tooltip="Total number of items",
            output_type="int",
            allowed_modes={ParameterMode.OUTPUT},
            default_value=0,
        )
        self.add_parameter(self.count)

        # Internal state for iteration
        self._current_index = 0
        self._items = []
        self._loop_completed = False
        self.flow = ControlFlow(name=self.name)

    def process(self) -> None:
        # Reset state when the node is first processed
        if "_iteration_started" not in self.parameter_values:
            self._initialize_loop()
            self.parameter_values["_iteration_started"] = True

        # If we're returning from the loop body, increment index for next iteration
        if "_returning_from_loop" in self.parameter_values:
            self._current_index += 1
            del self.parameter_values["_returning_from_loop"]

        # Update output values
        if self._current_index < len(self._items):
            # Set current item and index
            current_item = self._items[self._current_index]
            self.parameter_output_values["current_item"] = current_item
            self.parameter_output_values["index"] = self._current_index
            self._loop_completed = False
        else:
            # We've completed all iterations
            self._loop_completed = True

    def _initialize_loop(self) -> None:
        """Initialize the loop with items from the parameter list."""
        self._items = []
        self._current_index = 0

        # Collect all items from the parameter list
        for child in self.items_list.find_elements_by_type(Parameter, find_recursively=False):
            value = self.get_parameter_value(child.name)
            if value is not None:
                self._items.append(value)

        # Set the count output parameter
        self.parameter_output_values["count"] = len(self._items)

    def get_next_control_output(self) -> Optional[Parameter]:
        """Determine the next control flow path.

        Returns:
            The loop_body parameter if there are more items to process,
            or the completed parameter if all items have been processed.
        """
        if self._loop_completed:
            # Reset for next execution
            if "_iteration_started" in self.parameter_values:
                del self.parameter_values["_iteration_started"]
            return self.completed
        else:
            # Mark that we're entering the loop body
            self.parameter_values["_returning_from_loop"] = True
            return self.loop_body

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handle incoming connections to adapt parameter types if needed."""
        if (
            target_parameter.name.startswith("items.")
            and self.current_item.output_type == ParameterTypeBuiltin.ALL.value
        ):
            # Update the current_item output type to match the input type
            self.current_item.output_type = source_parameter.output_type



    @override
    def after_outgoing_connection(self, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter, modified_parameters_set: set[str]) -> None:
        # The target node needs to create its own flow.
        return super().after_outgoing_connection(source_parameter, target_node, target_parameter, modified_parameters_set)
