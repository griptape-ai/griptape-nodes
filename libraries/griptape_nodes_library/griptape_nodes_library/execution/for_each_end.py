from typing import Any, override

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode


class ForEachEndNode(EndLoopNode):
    """For Each End Node that completes a loop iteration and connects back to the ForEachStartNode.

    This node marks the end of a loop body and signals the ForEachStartNode to continue with the next item
    or to complete the loop if all items have been processed.
    """

    start_node_finished: bool
    output: ParameterList
    _index: int
    _children: list[Parameter]

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.start_node_finished = False
        self._index = 0
        self._children = []
        self.output = ParameterList(
            name="output",
            tooltip="Output parameter for the loop iteration",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)
        self.current_item = Parameter(
            name="current_item",
            tooltip="Current item in the loop",
            type=ParameterTypeBuiltin.ANY.value,
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.current_item)
        # Add control input parameter

    def process(self) -> None:
        if self._index == len(self._children):
            child = self.output.add_child_parameter()
            self._children.append(child)
        else:
            child = self._children[self._index]
        self.set_parameter_value(child.name,self.get_parameter_value("current_item"))
        self._index += 1
        if self.start_node_finished:
            while self._index < len(self._children)-1:
                self.output.remove_child(self._children[self._index])
                self._children.pop(self._index)
                self._index += 1
            self._index = 0

    def get_next_control_output(self) -> Parameter | None:
        """Return the loop_back parameter to continue the loop.

        This should connect back to the ForEachStartNode's exec_in parameter.
        If the node is finished, it moves on to the completed parameter.
        """
        if self.start_node_finished:
            self.start_node_finished = False
            return self.get_parameter_by_name("exec_out")
        return self.get_parameter_by_name("exec_in")
