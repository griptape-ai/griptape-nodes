from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeStartNode, StatusType


class ForLoopStartNode(BaseIterativeStartNode):
    """For Loop Start Node that runs a connected flow for a specified number of iterations.

    This node implements a traditional for loop with start, end, and step parameters.
    It provides the current iteration value to the next node in the flow and keeps track of the iteration state.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Track the current loop value directly
        self._current_value = 0

        # Adjust exec_out display name
        self.exec_out.ui_options = {"display_name": "For Loop"}

        # Adjust current_item to be an integer
        self.current_item.type = ParameterTypeBuiltin.INT.value

        # Add ForLoop-specific parameters
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

        # Move the parameter group to the end
        self.move_element_to_position("For Loop Item", position="last")

    def _get_compatible_end_classes(self) -> set[type]:
        """Return the set of End node classes that this Start node can connect to."""
        from griptape_nodes_library.execution.for_loop_end import ForLoopEndNode

        return {ForLoopEndNode}

    def _get_parameter_group_name(self) -> str:
        """Return the name for the parameter group containing iteration data."""
        return "For Loop Item"

    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over."""
        # Validate parameters
        validation_errors = self._validate_parameter_values()
        if validation_errors:
            raise validation_errors[0]  # Raise the first validation error

        # For ForLoop, we don't need to pre-calculate items
        # We'll use direct value comparison in is_loop_finished
        # Return a single-item list just to satisfy the base class contract
        return [True]

    def _initialize_iteration_data(self) -> None:
        """Initialize iteration-specific data and state."""
        # Set current value to start value
        start = self.get_parameter_value("start")
        self._current_value = start

    def _get_current_item_value(self) -> Any:
        """Get the current iteration value."""
        if not self.is_loop_finished():
            return self._current_value
        return None

    def is_loop_finished(self) -> bool:
        """Return True if the loop has reached the end condition."""
        end = self.get_parameter_value("end")
        step = self.get_parameter_value("step")

        # Check if we've reached or passed the end condition
        if step > 0:
            return self._current_value >= end
        if step < 0:
            return self._current_value <= end
        # step == 0, should have been caught in validation
        return True

    def _validate_parameter_values(self) -> list[Exception]:
        """Validate ForLoop parameter values."""
        exceptions = []
        start = self.get_parameter_value("start")
        end = self.get_parameter_value("end")
        step = self.get_parameter_value("step")

        if start < end and step <= 0:
            msg = f"{self.name}: Step value must be positive when start ({start}) is less than end ({end})"
            exceptions.append(Exception(msg))
        if start > end and step >= 0:
            msg = f"{self.name}: Step value must be negative when start ({start}) is greater than end ({end})"
            exceptions.append(Exception(msg))
        if start == end and step != 0:
            msg = f"{self.name}: Step value must be zero when start ({start}) is equal to end ({end})"
            exceptions.append(Exception(msg))
        if start != end and step == 0:
            msg = f"{self.name}: Step value must be non-zero when start ({start}) is not equal to end ({end})"
            exceptions.append(Exception(msg))

        return exceptions

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate before workflow run with ForLoop-specific checks."""
        exceptions = []

        # Add parameter validation
        if validation_exceptions := self._validate_parameter_values():
            exceptions.extend(validation_exceptions)

        # Reset loop state
        self._current_index = 0
        self._current_value = self.get_parameter_value("start")

        # Call parent validation
        parent_exceptions = super().validate_before_workflow_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None

    def process(self) -> None:
        """Override process to handle ForLoop-specific value advancement."""
        if self._flow is None:
            return

        # Handle different control entry points with direct logic
        match self._entry_control_parameter:
            case self.exec_in | None:
                # Starting the loop (initialization)
                self._initialize_loop()
                self._check_completion_and_set_output()
            case self.trigger_next_iteration_signal:
                # Next iteration signal from End - advance to next value
                step = self.get_parameter_value("step")
                self._current_value += step
                self._current_index += 1  # Keep this for status messages
                self._check_completion_and_set_output()
            case self.break_loop_signal:
                # Break signal from End - halt loop immediately
                self._complete_loop(StatusType.BREAK)
            case _:
                # Unexpected control entry point - log error for debugging
                err_str = f"ForLoop Start node '{self.name}' received unexpected control parameter: {self._entry_control_parameter}. "
                "Expected: exec_in, trigger_next_iteration_signal, break_loop_signal, or None."
                self._logger.error(err_str)
                return

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate before node run with ForLoop-specific checks."""
        exceptions = []

        # Add parameter validation
        if validation_exceptions := self._validate_parameter_values():
            exceptions.extend(validation_exceptions)

        # Call parent validation
        parent_exceptions = super().validate_before_node_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None
