from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.traits.clamp import Clamp
from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeStartNode


class ForLoopStartNode(BaseIterativeStartNode):
    """For Loop Start Node that runs a connected flow for a specified number of iterations.

    This node implements a traditional for loop with start, end, and step parameters.
    It provides the current iteration value to the next node in the flow and keeps track of the iteration state.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Track the current loop index directly
        self._current_index = 0

        # Add ForLoop-specific parameters
        self.start_value = Parameter(
            name="start",
            tooltip="Starting value for the loop",
            type=ParameterTypeBuiltin.INT.value,
            input_types=["int", "float"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=1,
        )
        self.end_value = Parameter(
            name="end",
            tooltip="Ending value for the loop",
            type=ParameterTypeBuiltin.INT.value,
            input_types=["int", "float"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=10,
        )
        self.end_inclusive = Parameter(
            name="end_inclusive",
            tooltip="Include the end value in the loop (True) or exclude it (False)",
            type=ParameterTypeBuiltin.BOOL.value,
            allowed_modes={ParameterMode.PROPERTY},
            default_value=True,
            ui_options={"display_name": "Include end value"},
        )
        self.step_value = Parameter(
            name="step",
            tooltip="Step size for each iteration (always positive)",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=1,
        )
        self.step_value.add_trait(Clamp(min_val=1, max_val=1000))

        # Order the Parameters
        self.add_parameter(self.start_value)
        self.add_parameter(self.end_value)
        self.add_parameter(self.end_inclusive)
        self.add_parameter(self.step_value)

        # Move the parameter group to the end
        self.move_element_to_position("For Loop", position="last")

        # Move the status message to the very bottom
        self.move_element_to_position("status_message", position="last")

    def _get_compatible_end_classes(self) -> set[type]:
        """Return the set of End node classes that this Start node can connect to."""
        from griptape_nodes_library.execution.for_loop_end import ForLoopEndNode

        return {ForLoopEndNode}

    def _get_parameter_group_name(self) -> str:
        """Return the name for the parameter group containing iteration data."""
        return "For Loop"

    def _get_exec_out_display_name(self) -> str:
        """Return the display name for the exec_out parameter."""
        return "On Each"

    def _get_exec_out_tooltip(self) -> str:
        """Return the tooltip for the exec_out parameter."""
        return "Execute for each iteration"

    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over."""
        # ForLoop doesn't use items - this method is not used
        # We keep it for compatibility but it's not called anymore
        return []

    def _initialize_iteration_data(self) -> None:
        """Initialize iteration-specific data and state."""
        # Set current index to start value
        start = self.get_parameter_value("start")
        self._current_index = start

    def _get_current_item_value(self) -> Any:
        """Get the current iteration value."""
        if not self.is_loop_finished():
            return self._current_index
        return None

    def is_loop_finished(self) -> bool:
        """Return True if the loop has reached the end condition."""
        start = self.get_parameter_value("start")
        end = self.get_parameter_value("end")
        end_inclusive = self.get_parameter_value("end_inclusive")

        # Determine direction based on start and end values
        ascending = start <= end

        # Check if we've reached or passed the end condition
        if ascending:
            if end_inclusive:
                return self._current_index > end
            return self._current_index >= end
        # descending
        if end_inclusive:
            return self._current_index < end
        return self._current_index <= end

    def _get_total_iterations(self) -> int:
        """Return the total number of iterations for this loop."""
        start = self.get_parameter_value("start")
        end = self.get_parameter_value("end")
        step = self.get_parameter_value("step")
        end_inclusive = self.get_parameter_value("end_inclusive")

        if step <= 0:
            return 0

        # Determine direction and calculate iterations
        if start <= end:  # ascending
            if end_inclusive:
                return max(0, (end - start) // step + 1)
            return max(0, (end - start + step - 1) // step)
        # descending
        if end_inclusive:
            return max(0, (start - end) // step + 1)
        return max(0, (start - end + step - 1) // step)

    def _get_current_iteration_count(self) -> int:
        """Return the current iteration count (0-based)."""
        return self._current_iteration_count

    def get_current_index(self) -> int:
        """Return the current loop value (start, start+step, start+2*step, ...)."""
        return self._current_index

    def _advance_to_next_iteration(self) -> None:
        """Advance to the next iteration by step amount in the appropriate direction."""
        start = self.get_parameter_value("start")
        end = self.get_parameter_value("end")
        step = self.get_parameter_value("step")

        # Determine direction and apply step accordingly
        if start <= end:  # ascending
            self._current_index += step
        else:  # descending
            self._current_index -= step
        self._current_iteration_count += 1

    def _validate_parameter_values(self) -> list[Exception]:
        """Validate ForLoop parameter values."""
        exceptions = []
        start = self.get_parameter_value("start")
        end = self.get_parameter_value("end")
        step = self.get_parameter_value("step")
        end_inclusive = self.get_parameter_value("end_inclusive")

        # Step must always be positive (>= 1)
        if step < 1:
            msg = f"{self.name}: Step value must be positive (>= 1), got {step}"
            exceptions.append(Exception(msg))

        # Informational logging for edge cases
        if start == end:
            if end_inclusive:
                # With end_inclusive=True and start==end, we execute exactly 1 iteration
                self._logger.info(
                    "%s: Loop will execute 1 iteration since start (%s) equals end (%s) and end_inclusive is True.",
                    self.name,
                    start,
                    end,
                )
            else:
                # With end_inclusive=False and start==end, we execute 0 iterations
                self._logger.info(
                    "%s: Loop will execute 0 iterations since start (%s) equals end (%s) and end_inclusive is False.",
                    self.name,
                    start,
                    end,
                )

        return exceptions

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate before workflow run with ForLoop-specific checks."""
        exceptions = []

        # Add parameter validation
        if validation_exceptions := self._validate_parameter_values():
            exceptions.extend(validation_exceptions)

        # Reset loop state
        self._current_iteration_count = 0
        self._current_index = self.get_parameter_value("start")

        # Call parent validation
        parent_exceptions = super().validate_before_workflow_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None

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
