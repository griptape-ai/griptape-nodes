from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode, StartLoopNode


class ForLoopEndNode(EndLoopNode):
    """For Loop End Node that completes a loop iteration and connects back to the ForLoopStartNode.

    This node marks the end of a loop body and signals the ForLoopStartNode to continue with the next iteration
    or to complete the loop if all iterations have been processed.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.start_node = None
        self.continue_loop = ControlParameterOutput(tooltip="Continue to the next iteration", name="exec_out")
        self.from_start = ControlParameterInput(
            tooltip="Continue to the next iteration",
            name="from_start",
        )
        self.from_start.ui_options = {"hide": True}
        self.add_parameter(self.continue_loop)
        self.add_parameter(self.from_start)

        self.current_value = Parameter(
            name="current_value",
            tooltip="Current value in the loop",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.current_value)

    def validate_before_node_run(self) -> list[Exception] | None:
        if self.start_node is None:
            return [Exception("Start node is not set on End Node.")]
        return super().validate_before_node_run()

    def validate_before_workflow_run(self) -> list[Exception] | None:
        if self.start_node is None:
            return [Exception("Start node is not set on End Node.")]
        return super().validate_before_node_run()

    def process(self) -> None:
        if self.start_node is None:
            return

    def get_next_control_output(self) -> Parameter | None:
        """Return the loop_back parameter to continue the loop.

        This should connect back to the ForLoopStartNode's exec_in parameter.
        If the node is finished, it moves on to the completed parameter.
        """
        # Go back to the start node now.
        if self.start_node is not None and self.start_node.finished:
            return self.get_parameter_by_name("exec_out")
        return self.get_parameter_by_name("from_start")

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        if target_parameter is self.from_start and isinstance(source_node, StartLoopNode):
            self.start_node = source_node
        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )
