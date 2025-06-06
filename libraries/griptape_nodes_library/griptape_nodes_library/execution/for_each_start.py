from typing import Any

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

    _items: list[Any]
    _flow: ControlFlow | None = None

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.finished = False
        self.current_index = 0
        self._items = []
        self.exec_out = ControlParameterOutput(tooltip="Continue the flow", name="exec_out")
        self.add_parameter(self.exec_out)
        self.exec_in = ControlParameterInput()
        self.add_parameter(self.exec_in)
        self.index_count = Parameter(
            name="index",
            tooltip="Current index of the iteration",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.PROPERTY},
            settable=False,
            default_value=0,
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

        self.loop = ControlParameterOutput(tooltip="Enter the For Each Loop", name="loop")
        self.add_parameter(self.loop)

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._flow is None:
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
        # Check if we're done.
        if self.current_index == len(self._items):
            # This is the last iteration of the loop
            self.finished = True
            # reset the node.
            self.current_index = 0
            self._items = []

    # This node cannot run unless it's connected to a start node.
    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        self.current_index = 0
        self._items = []
        self.finished = False
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
        if self.finished:
            self.finished = False
            return self.exec_out
        return self.loop

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if target_parameter == self.items_list or target_parameter.parent_container_name == "items":
            self.current_item.type = source_parameter.type
            modified_parameters_set.add("current_item")
        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )
