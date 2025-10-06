from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeStartNode


class ForEachStartNode(BaseIterativeStartNode):
    """For Each Start Node that runs a connected flow for each item in a list or dictionary.

    This node iterates through each item in the input list or dictionary and runs the connected flow for each item.
    For lists, it provides each item directly. For dictionaries, it provides {"key": k, "value": v} for each entry.
    It keeps track of the iteration state and current index.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # ForEach-specific state
        self._items: list[Any] | None = None

        # Add ForEach-specific parameters
        self.items_list = Parameter(
            name="items",
            tooltip="List or dictionary to iterate through",
            input_types=["list", "dict"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        # Add current_item parameter specific to ForEach
        self.current_item = Parameter(
            name="current_item",
            tooltip="Current item being processed",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
            settable=False,
        )
        # Find the parameter group and add the current_item parameter
        group = self.get_group_by_name_or_element_id("For Each Item")
        if group:
            group.add_child(self.current_item)

    def _get_compatible_end_classes(self) -> set[type]:
        """Return the set of End node classes that this Start node can connect to."""
        from griptape_nodes_library.execution.for_each_end import ForEachEndNode

        return {ForEachEndNode}

    def _get_parameter_group_name(self) -> str:
        """Return the name for the parameter group containing iteration data."""
        return "For Each Item"

    def _get_exec_out_display_name(self) -> str:
        """Return the display name for the exec_out parameter."""
        return "On Each Item"

    def _get_exec_out_tooltip(self) -> str:
        """Return the tooltip for the exec_out parameter."""
        return "Execute for each item in the list or dictionary"

    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over.

        Accepts either a list or dict. If dict, converts to list of {"key": k, "value": v} dicts.
        """
        items = self.get_parameter_value("items")

        # Handle case where items parameter is not connected or has no value
        if items is None:
            self._logger.info("ForEach Start '%s': No items provided, skipping loop execution", self.name)
            return []

        # Handle dict input - convert to list of {"key": k, "value": v} dicts
        if isinstance(items, dict):
            if len(items) == 0:
                self._logger.info("ForEach Start '%s': Empty dictionary provided, skipping loop execution", self.name)
                return []
            return [{"key": k, "value": v} for k, v in items.items()]

        # Handle list input
        if isinstance(items, list):
            if len(items) == 0:
                self._logger.info("ForEach Start '%s': Empty list provided, skipping loop execution", self.name)
            return items

        # Invalid type
        error_msg = f"ForEach Start '{self.name}' expected a list or dict but got {type(items).__name__}: {items}"
        raise TypeError(error_msg)

    def _initialize_iteration_data(self) -> None:
        """Initialize iteration-specific data and state."""
        # Get the items list for ForEach
        self._items = self._get_iteration_items()

    def is_loop_finished(self) -> bool:
        """Return True if the loop has completed all items or has no items to process."""
        if not self._items or len(self._items) == 0:
            return True
        return self._current_iteration_count >= len(self._items)

    def _get_total_iterations(self) -> int:
        """Return the total number of iterations for this loop."""
        return len(self._items) if self._items else 0

    def _get_current_iteration_count(self) -> int:
        """Return the current iteration count (0-based)."""
        return self._current_iteration_count

    def get_current_index(self) -> int:
        """Return the current array position (0, 1, 2, ...)."""
        return self._current_iteration_count

    def _advance_to_next_iteration(self) -> None:
        """Advance to the next iteration by incrementing the index by 1."""
        self._current_iteration_count += 1

    def _get_current_item_value(self) -> Any:
        """Get the current iteration value."""
        if self._items and self._current_iteration_count < len(self._items):
            current_item_value = self._items[self._current_iteration_count]
            # Set the current_item output parameter
            self.parameter_output_values["current_item"] = current_item_value
            self.publish_update_to_parameter("current_item", current_item_value)
            return current_item_value
        return None

    def _validate_iterative_connections(self) -> list[Exception]:
        """Validate ForEach-specific connections in addition to base validation."""
        errors = super()._validate_iterative_connections()
        # Removed validation for 'items' parameter connection to allow workflow execution
        # when no items are provided - the loop will simply skip execution gracefully
        return errors
