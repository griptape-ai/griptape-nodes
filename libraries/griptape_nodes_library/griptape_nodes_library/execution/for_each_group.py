"""ForEach Group Node - A single node that iterates over items with an encapsulated loop body."""

from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_groups import BaseIterativeNodeGroup

logger = logging.getLogger("griptape_nodes")


class ForEachGroupNode(BaseIterativeNodeGroup):
    """ForEach Group Node that iterates over a list or dictionary.

    This node combines the functionality of ForEachStartNode and ForEachEndNode
    into a single group node. Child nodes added to the group become the loop body
    and are executed for each item in the input list or dictionary.

    Parameters:
        items (input): List or dictionary to iterate through
        current_item (output, left): Current item being processed - connect to internal nodes
        index (output, left): Current iteration index - connect to internal nodes
        new_item_to_add (input, right): Item to collect from each iteration
        results (output, right): Collected results from all iterations

    The node supports both sequential and parallel execution modes via the
    'run_in_order' property, and can execute locally, in a private subprocess,
    or via cloud services depending on the 'execution_environment' setting.
    """

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # ForEach-specific: items input parameter (left side)
        self.items_param = Parameter(
            name="items",
            tooltip="List or dictionary to iterate through",
            input_types=["list", "dict"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_param)

        # Add to left parameters for UI layout (insert at beginning)
        if "left_parameters" in self.metadata:
            self.metadata["left_parameters"].insert(0, "items")
        else:
            self.metadata["left_parameters"] = ["items"]

        # ForEach-specific: current_item output parameter (left side - feeds into group)
        self.current_item = Parameter(
            name="current_item",
            tooltip="Current item being processed",
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.OUTPUT},
            settable=False,
        )
        self.add_parameter(self.current_item)

        # Add current_item to left parameters (after items, before index)
        if "left_parameters" in self.metadata:
            # Insert after items but before index
            idx = self.metadata["left_parameters"].index("index")
            self.metadata["left_parameters"].insert(idx, "current_item")
        else:
            self.metadata["left_parameters"] = ["items", "current_item", "index"]

        self.move_element_to_position("items", 0)
        self.move_element_to_position("results", 1)
        self.move_element_to_position("run_in_order", 2)
        self.add_parameter_to_group_settings(self.run_in_order)

    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over.

        Accepts either a list or dict. If dict, converts to list of {"key": k, "value": v} dicts.
        """
        items = self.get_parameter_value("items")

        # Handle case where items parameter is not connected or has no value
        if items is None:
            logger.info("ForEach Group '%s': No items provided, skipping loop execution", self.name)
            return []

        # Handle dict input - convert to list of {"key": k, "value": v} dicts
        if isinstance(items, dict):
            if len(items) == 0:
                logger.info("ForEach Group '%s': Empty dictionary provided, skipping loop execution", self.name)
                return []
            return [{"key": k, "value": v} for k, v in items.items()]

        # Handle list input
        if isinstance(items, list):
            if len(items) == 0:
                logger.info("ForEach Group '%s': Empty list provided, skipping loop execution", self.name)
            return items

        # Invalid type
        error_msg = f"ForEach Group '{self.name}' expected a list or dict but got {type(items).__name__}: {items}"
        raise TypeError(error_msg)

    def _get_current_item_value(self, iteration_index: int) -> Any:
        """Get the current item value for a specific iteration.

        Args:
            iteration_index: 0-based iteration index

        Returns:
            The item at the given index, or None if out of bounds
        """
        if self._items and iteration_index < len(self._items):
            return self._items[iteration_index]
        return None

    def get_current_index(self) -> int:
        """Return the current array position (0, 1, 2, ...)."""
        return self._current_iteration_count
