from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes_library.execution.for_each_start import ForEachStartNode


class ForLoopStartNode(ForEachStartNode):
    """For Loop Start Node that runs a connected flow for a specified number of iterations.

    This node implements a traditional for loop with start, end, and step parameters.
    It provides the current iteration value to the next node in the flow and keeps track of the iteration state.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Set up internal state tracking
        self._internal_index = 0
        self._offset = 0
        self._internal_end = 0
        self.current_index = 0
        self.exec_out.ui_options = {"display_name": "For Loop"}

        # Delete existing parameters we don't need
        self.remove_parameter_element_by_name("index")
        self.remove_parameter_element_by_name("items")

        # Adjust current_item to be an integer
        self.current_item.type = ParameterTypeBuiltin.INT.value

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

        self.add_parameter(self.start_value)
        self.add_parameter(self.end_value)
        self.add_parameter(self.step_value)

        self.move_element_to_position("For Each Item", position="last")

    def process(self) -> None:
        # Reset state when the node is first processed
        if self._flow is None or self.finished:
            return

        if self._internal_index == 0:
            # Initialize everything!
            start = self.get_parameter_value("start")
            end = self.get_parameter_value("end")
            step = self.get_parameter_value("step")
            if step <= 0:
                # We should have caught this in validation, but just in case
                msg = f"{self.name}: Step value cannot be less than or equal to zero"
                raise ValueError(msg)

            # Calculate internal range starting from 0
            self._offset = start
            # Calculate how many steps we need to take
            self._internal_end = (end - start) // step
            self._internal_index = 0
            self.current_index = 0  # Start at 0 for proper end node synchronization

        # Unresolve all future nodes at the start of processing
        self._flow.connections.unresolve_future_nodes(self)

        # Get the current value and pass it along
        step = self.get_parameter_value("step")
        current_value = self._offset + (self._internal_index * step)
        self.parameter_output_values["current_item"] = current_value  # Pass current value to end node

        self.current_index = self._internal_index + 1  # 1-based for end node compatibility
        self._internal_index += 1

        # Check if we've reached the end
        if self._internal_index > self._internal_end:
            self.finished = True
            self._internal_index = 0
            self.current_index = 0

    def _validate_parameter_values(self) -> list[Exception] | None:
        exceptions = []
        if self.get_parameter_value("start") >= self.get_parameter_value("end"):
            exceptions.append(Exception(f"{self.name}: Start value must be less than end value"))

        if self.get_parameter_value("step") <= 0:
            exceptions.append(Exception(f"{self.name}: Step value cannot be less than or equal to zero"))

        return exceptions

    def validate_before_workflow_run(self) -> list[Exception] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        exceptions = []

        if validation_exceptions := self._validate_parameter_values():
            exceptions.extend(validation_exceptions)

        self._internal_index = 0
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
        if validation_exceptions := self._validate_parameter_values():
            exceptions.extend(validation_exceptions)

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
