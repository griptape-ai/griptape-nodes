"""Base class for iterative node groups (ForEach, ForLoop, etc.)."""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup

logger = logging.getLogger("griptape_nodes")


class BaseIterativeNodeGroup(SubflowNodeGroup):
    """Base class for iterative node groups (ForEach, ForLoop, etc.).

    Combines the functionality of BaseIterativeStartNode and BaseIterativeEndNode
    into a single group node that encapsulates the loop body as child nodes.

    This provides a simpler user experience than separate start/end nodes while
    maintaining the same execution capabilities (sequential/parallel, local/private/cloud).

    The NodeExecutor detects instances of this class and handles iteration execution
    via handle_iterative_group_execution(), similar to how it handles BaseIterativeEndNode.

    Subclasses must implement:
        - _get_iteration_items(): Return the list of items to iterate over
        - _get_current_item_value(iteration_index): Get the value for current iteration
    """

    # Iteration state
    _items: list[Any]
    _current_iteration_count: int
    _total_iterations: int
    is_parallel: bool

    # Results storage
    _results_list: list[Any]

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Initialize iteration state
        self._items = []
        self._current_iteration_count = 0
        self._total_iterations = 0
        self.is_parallel = False
        self._results_list = []

        # Add parallel execution control parameter
        self.run_in_order = Parameter(
            name="run_in_order",
            tooltip="Execute all iterations in order or concurrently",
            type=ParameterTypeBuiltin.BOOL.value,
            allowed_modes={ParameterMode.PROPERTY},
            default_value=True,
            ui_options={"display_name": "Run in Order"},
        )
        self.add_parameter(self.run_in_order)

        # Index parameter - available in all iterative nodes (left side - feeds into group)
        self.index_param = Parameter(
            name="index",
            tooltip="Current index of the iteration",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.OUTPUT},
            settable=False,
            default_value=0,
        )
        self.add_parameter(self.index_param)

        # Track left parameters for UI layout
        if "left_parameters" not in self.metadata:
            self.metadata["left_parameters"] = []
        self.metadata["left_parameters"].append("index")

        # Results collection parameters (right side - collects from group)
        self.new_item_to_add = Parameter(
            name="new_item_to_add",
            tooltip="Item to add to results list for each iteration",
            type=ParameterTypeBuiltin.ANY.value,
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.new_item_to_add)

        self.results = Parameter(
            name="results",
            tooltip="Collected results from all iterations",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.results)

        # Track right parameters for UI layout
        if "right_parameters" not in self.metadata:
            self.metadata["right_parameters"] = []
        self.metadata["right_parameters"].extend(["new_item_to_add", "results"])

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes."""
        super().after_value_set(parameter, value)
        if parameter == self.run_in_order:
            self.is_parallel = not value

    @abstractmethod
    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over.

        Returns:
            List of items for iteration. Empty list if no items.
        """

    @abstractmethod
    def _get_current_item_value(self, iteration_index: int) -> Any:
        """Get the value for a specific iteration.

        Args:
            iteration_index: 0-based iteration index

        Returns:
            The value to use for this iteration
        """

    def _initialize_iteration_data(self) -> None:
        """Initialize iteration-specific data and state."""
        self._items = self._get_iteration_items()
        self._total_iterations = len(self._items) if self._items else 0
        self._current_iteration_count = 0
        self._results_list = []

    def _get_total_iterations(self) -> int:
        """Return the total number of iterations for this loop."""
        return self._total_iterations

    def get_all_iteration_values(self) -> list[int]:
        """Calculate and return all iteration index values.

        For ForEach nodes, this returns indices 0, 1, 2, ...
        For ForLoop nodes, this could return actual loop values.

        Returns:
            List of integer values for each iteration
        """
        return list(range(self._get_total_iterations()))

    def _output_results_list(self) -> None:
        """Output the current results list to the results parameter."""
        import copy

        self.parameter_output_values["results"] = copy.deepcopy(self._results_list)

    def reset_for_workflow_run(self) -> None:
        """Reset state for a fresh workflow run."""
        self._results_list = []
        self._current_iteration_count = 0
        self._total_iterations = 0
        self._output_results_list()

    async def aprocess(self) -> None:
        """Execute the iterative node group.

        Note: This method is typically not called directly. The NodeExecutor
        detects BaseIterativeNodeGroup instances and calls handle_iterative_group_execution()
        instead. This implementation exists as a fallback for direct local execution.
        """
        # For direct local execution (when NodeExecutor doesn't intercept),
        # just execute the subflow once. The NodeExecutor handles iteration logic.
        await self.execute_subflow()
