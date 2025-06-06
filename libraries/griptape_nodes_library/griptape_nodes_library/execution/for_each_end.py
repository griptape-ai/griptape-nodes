from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterOutput,
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode, StartLoopNode


class ForEachEndNode(EndLoopNode):
    """For Each End Node that completes a loop iteration and connects back to the ForEachStartNode.

    This node marks the end of a loop body and signals the ForEachStartNode to continue with the next item
    or to complete the loop if all items have been processed.
    """

    output: Parameter

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.start_node = None
        self._index = 0
        self.continue_loop = ControlParameterOutput(tooltip="Continue to the next iteration", name="Continue")
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
        if self.start_node is None:
            return [Exception("Start node is not set on End Node.")]
        return super().validate_before_node_run()

    def validate_before_workflow_run(self) -> list[Exception] | None:
        self._index = 0
        if self.start_node is None:
            return [Exception("Start node is not set on End Node.")]
        return super().validate_before_node_run()

    def process(self) -> None:
        if self.start_node is None:
            return
        if self.start_node.current_index == 0:
            self.remove_parameter_value("output")
        output_list = self.get_parameter_value("output")
        output_list.append(self.get_parameter_value("current_item"))
        if self.start_node.finished:
            self.parameter_output_values["output"] = self.get_parameter_value("output")

    def get_next_control_output(self) -> Parameter | None:
        """Return the loop_back parameter to continue the loop.

        This should connect back to the ForEachStartNode's exec_in parameter.
        If the node is finished, it moves on to the completed parameter.
        """
        # Go back to the start node now.
        return self.get_parameter_by_name("Continue")

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,
        target_parameter: Parameter,
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        if target_parameter is self.continue_loop and isinstance(target_node, StartLoopNode):
            self.start_node = target_node
