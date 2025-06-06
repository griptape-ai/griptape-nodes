from typing import Any, override

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
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
    output: Parameter
    _index: int
    _children: list[Parameter]

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.start_node_finished = False
        self._index = 0
        self._children = []
        self.continue_loop = ControlParameterOutput(
            tooltip = "Continue to the next iteration",
            name="Continue"
        )
        self.add_parameter(self.continue_loop)
        self.output = Parameter(
            name="output",
            tooltip="Output parameter for the loop iteration",
            output_type="list",
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

    def validate_before_node_run(self) -> list[Exception] | None:
        self._index = 0
        self.start_node_finished = False
        return super().validate_before_node_run()

    @override
    def validate_before_workflow_run(self) -> list[Exception] | None:
        self._index = 0
        self.start_node_finished = False
        return super().validate_before_workflow_run()

    def process(self) -> None:
        output_list = self.get_parameter_value("output")
        output_list.append(self.get_parameter_value("current_item"))
        self._index += 1
        if self.start_node_finished:
            self.parameter_output_values["output"] = self.get_parameter_value
            while self._index < len(self._children) - 1:
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

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        modified_parameters_set.add("output")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        modified_parameters_set.add("output")
        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )
