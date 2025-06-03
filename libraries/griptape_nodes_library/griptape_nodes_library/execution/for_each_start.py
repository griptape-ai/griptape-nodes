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

from libraries.griptape_nodes_library.griptape_nodes_library.execution.for_each_end import ForEachEndNode


class ForEachStartNode(StartLoopNode):
    """For Each Start Node that runs a connected flow for each item in a parameter list.

    This node iterates through each item in the input list and runs the connected flow for each item.
    It provides the current item to the next node in the flow and keeps track of the iteration state.
    """
    for_each_end: ForEachEndNode
    _current_index: int
    _items: list[Any]

    def __init__(self, name: str, for_each_end: ForEachEndNode, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.for_each_end = for_each_end
        self._current_index = 0
        self._items = []
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

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._current_index == 0:
            # Initialize everything!
            list_values = self.get_parameter_value("items")
            self._items = list_values
        # Get the current item and pass it along.
        # I need to unresolve all future nodes (all of them in the for each loop).
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        flow = GriptapeNodes.ObjectManager().get_object_by_name(GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name))
        if isinstance(flow, ControlFlow):
            # Unresolve all nodes in the flow from this guy!
            flow.connections.unresolve_future_nodes(self)
        current_item_value = self._items[self._current_index]
        self.parameter_output_values["current_item"] = current_item_value
        self._current_index += 1
        # Check if we're done.
        if self._current_index < len(self._items) - 1:
            # This is the last iteration of the loop
            self.for_each_end.start_node_finished = True
            # reset the node.
            self._current_index = 0
            self._items = []

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handle incoming connections to adapt parameter types if needed."""
        if (
            target_parameter.name.startswith("items")
            and self.current_item.output_type == ParameterTypeBuiltin.ALL.value
        ):
            # Update the current_item output type to match the input type
            self.current_item.output_type = source_parameter.output_type

