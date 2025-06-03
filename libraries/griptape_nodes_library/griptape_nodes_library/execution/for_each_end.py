from typing import Any, Optional

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter, ParameterList, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import EndLoopNode, BaseNode


class ForEachEndNode(EndLoopNode):
    """For Each End Node that completes a loop iteration and connects back to the ForEachStartNode.

    This node marks the end of a loop body and signals the ForEachStartNode to continue with the next item
    or to complete the loop if all items have been processed.
    """
    start_node_finished: bool

    def __init__(self, name: str, loop_id:str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.loop_id = loop_id
        self.start_node_finished = False
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
            type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.INPUT}
        )
        # Add control input parameter

    def process(self) -> None:
        child = self.output.add_child_parameter()
        self.set_parameter_value(child.name, self.get_parameter_value("current_item"))


    def get_next_control_output(self) -> Optional[Parameter]:
        """Return the loop_back parameter to continue the loop.

        This should connect back to the ForEachStartNode's exec_in parameter.
        If the node is finished, it moves on to the completed parameter.
        """
        if self.start_node_finished:
            return self.get_parameter_by_name("exec_out")
        return self.get_parameter_by_name("exec_in")
