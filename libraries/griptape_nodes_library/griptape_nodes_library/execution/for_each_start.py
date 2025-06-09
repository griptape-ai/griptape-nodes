from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterList,
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

    _items: list[Any]
    _flow: ControlFlow | None = None

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.finished = False
        self.current_index = 0
        self._items = []
        self.exec_out = ControlParameterOutput(tooltip="Continue the flow", name="exec_out")
        self.exec_out.ui_options = {"display_name": "For Each"}
        self.add_parameter(self.exec_out)
        self.exec_in = ControlParameterInput()
        self.add_parameter(self.exec_in)
        self.items_list = ParameterList(
            name="items",
            tooltip="List of items to iterate through",
            input_types=[ParameterTypeBuiltin.ANY.value],
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
            )
            self.index_count = Parameter(
                name="index",
                tooltip="Current index of the iteration",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                settable=False,
                default_value=0,
            )
        self.add_node_element(group)

        self.loop = ControlParameterOutput(tooltip="To the End Node", name="loop")
        self.loop.ui_options = {"display_name": "Enter Loop", "hide": True}
        self.add_parameter(self.loop)

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._flow is None or self.finished:
            return
        if self.current_index == 0:
            # Initialize everything!
            list_values = self.get_parameter_value("items")
            self._items = list_values
        # Get the current item and pass it along.
        # I need to unresolve all future nodes (all of them in the for each loop).
        self._flow.connections.unresolve_future_nodes(self)
        current_item_value = self._items[self.current_index]
        self.parameter_output_values["current_item"] = current_item_value
        self.set_parameter_value("index", self.current_index)
        self.publish_update_to_parameter("index", self.current_index)
        self.current_index += 1
        if self.current_index == len(self._items):
            self.finished = True
            self._items = []
            self.current_index = 0

    # This node cannot run unless it's connected to a start node.
    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        self.current_index = 0
        self._items = []
        self.finished = False
        if self.end_node is None:
            exceptions.append(Exception("End node not found or connected."))
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
            exceptions.append(Exception("End node not found or connected."))
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
        return self.loop

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if source_parameter == self.loop and isinstance(target_node, EndLoopNode):
            self.end_node = target_node
        return super().after_outgoing_connection(
            source_parameter, target_node, target_parameter, modified_parameters_set
        )
