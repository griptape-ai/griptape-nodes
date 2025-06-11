from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, EndLoopNode, StartLoopNode


class ForLoopStartNode(StartLoopNode):
    """For Loop Start Node that runs a connected flow for a specified number of iterations.

    This node implements a traditional for loop with start, end, and step parameters.
    It provides the current iteration value to the next node in the flow and keeps track of the iteration state.
    """

    _flow: ControlFlow | None = None

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.finished = False
        self.current_index = 0
        self.exec_out = ControlParameterOutput(tooltip="Continue the flow", name="exec_out")
        self.exec_out.ui_options = {"display_name": "For Loop"}
        self.add_parameter(self.exec_out)
        self.exec_in = ControlParameterInput()
        self.add_parameter(self.exec_in)

        with ParameterGroup(name="Loop Parameters") as group:
            self.start_value = Parameter(
                name="start",
                tooltip="Starting value for the loop",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=1,
            )
            self.end_value = Parameter(
                name="end",
                tooltip="Ending value for the loop (exclusive)",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=10,
            )
            self.step_value = Parameter(
                name="step",
                tooltip="Step value for each iteration",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=1,
            )
            self.current_index_param = Parameter(
                name="current_index",
                tooltip="Current value in the loop",
                type=ParameterTypeBuiltin.INT.value,
                allowed_modes={ParameterMode.OUTPUT},
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
            self.current_index = self.get_parameter_value("start")
            self.end = self.get_parameter_value("end")
            self.step = self.get_parameter_value("step")
            if self.step == 0:
                raise ValueError("Step value cannot be zero")

        # Get the current value and pass it along
        self._flow.connections.unresolve_future_nodes(self)
        self.parameter_output_values["current_index"] = self.current_index
        self.current_index += self.step

        # Check if we've reached the end
        if (self.step > 0 and self.current_index >= self.end) or (self.step < 0 and self.current_index <= self.end):
            self.finished = True
            self.current_index = 0

    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []
        self.current_index = 0
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
