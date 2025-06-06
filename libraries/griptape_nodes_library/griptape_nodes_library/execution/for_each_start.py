from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterType,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode, StartLoopNode


class ForEachStartNode(StartLoopNode):
    """For Each Start Node that runs a connected flow for each item in a parameter list.

    This node iterates through each item in the input list and runs the connected flow for each item.
    It provides the current item to the next node in the flow and keeps track of the iteration state.
    """

    for_each_end: EndLoopNode | None
    _current_index: int
    _items: list[Any]
    _flow: ControlFlow | None = None

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.for_each_end = None
        self._current_index = 0
        self._items = []
        self.index_count = Parameter(
            name="index",
            tooltip="Current index of the iteration",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.PROPERTY},
            settable=False,
            default_value=0
        )
        self.add_parameter(self.index_count)
        self.items_list = ParameterList(
            name="items",
            tooltip="List of items to iterate through",
            input_types=[ParameterTypeBuiltin.ANY.value],
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
        if self.for_each_end is None or self._flow is None:
            return
        if self._current_index == 0:
            # Initialize everything!
            list_values = self.get_parameter_value("items")
            self._items = list_values
        # Get the current item and pass it along.
        # I need to unresolve all future nodes (all of them in the for each loop).
        self._flow.connections.unresolve_future_nodes(self)
        current_item_value = self._items[self._current_index]
        self.parameter_output_values["current_item"] = current_item_value
        self.set_parameter_value("index", self._current_index)
        self.publish_update_to_parameter("index", self._current_index)
        self._current_index += 1
        # Check if we're done.
        if self._current_index == len(self._items):
            # This is the last iteration of the loop
            self.for_each_end.start_node_finished = True
            # reset the node.
            self._current_index = 0
            self._items = []

    # This node cannot run unless it's connected to a start node.
    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        self._current_index = 0
        self._items = []
        try:
            flow = GriptapeNodes.ObjectManager().get_object_by_name(
                GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
            )
            if isinstance(flow, ControlFlow):
                self._flow = flow
        except Exception as e:
            exceptions.append(e)
        if self.for_each_end is None:
            exceptions.append([Exception("ForEachEndNode does not exist")])
        return exceptions

    # This node cannot be run unless it's connected to an end node.
    def validate_before_node_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        try:
            flow = GriptapeNodes.ObjectManager().get_object_by_name(
                GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
            )
            if isinstance(flow, ControlFlow):
                self._flow = flow
        except Exception as e:
            exceptions.append(e)
        if self.for_each_end is None:
            exceptions.append([Exception("ForEachEndNode does not exist")])
        return exceptions

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if isinstance(target_node, EndLoopNode) and self.for_each_end is None:
            self.for_each_end = target_node
            output_param = target_node.get_parameter_by_name("output")
            if not isinstance(output_param, ParameterList):
                return None
            for _ in range(len(self.items_list._children) - len(output_param._children)):
                new_child = output_param.add_child_parameter()
                target_node._children.append(new_child)
        return super().after_outgoing_connection(
            source_parameter, target_node, target_parameter, modified_parameters_set
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if self.for_each_end is None:
            return None
        output_param = self.for_each_end.get_parameter_by_name("output")
        if not isinstance(output_param, ParameterList):
            return None
        for _ in range(len(parameter._children) - len(output_param._children)):
            self.for_each_end._children.append(output_param.add_child_parameter())
        return super().after_value_set(parameter, value, modified_parameters_set)

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if isinstance(target_node, EndLoopNode) and self.for_each_end is target_node:
            self.for_each_end = None
        return super().after_outgoing_connection_removed(
            source_parameter, target_node, target_parameter, modified_parameters_set
        )
