from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes_library.execution.base_iterative_nodes import BaseIterativeStartNode


class ForEachStartNode(BaseIterativeStartNode):
    """For Each Start Node that runs a connected flow for each item in a parameter list.

    This node iterates through each item in the input list and runs the connected flow for each item.
    It provides the current item to the next node in the flow and keeps track of the iteration state.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add ForEach-specific parameters
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to iterate through",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        # Add index parameter to the parameter group
        self.index_count = Parameter(
            name="index",
            tooltip="Current index of the iteration",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            settable=False,
            default_value=0,
            ui_options={"hide_property": True},
        )
        # Find the parameter group and add the index parameter
        group = self.get_group_by_name_or_element_id("For Each Item")
        if group:
            group.add_child(self.index_count)

    def _get_compatible_end_classes(self) -> set[type]:
        """Return the set of End node classes that this Start node can connect to."""
        from griptape_nodes_library.execution.for_each_end import ForEachEndNode

        return {ForEachEndNode}

    def _get_parameter_group_name(self) -> str:
        """Return the name for the parameter group containing iteration data."""
        return "For Each Item"

    def _get_iteration_items(self) -> list[Any]:
        """Get the list of items to iterate over."""
        list_values = self.get_parameter_value("items")
        if not isinstance(list_values, list):
            error_msg = (
                f"ForEach Start '{self.name}' expected a list but got {type(list_values).__name__}: {list_values}"
            )
            raise TypeError(error_msg)
        return list_values

    def _initialize_iteration_data(self) -> None:
        """Initialize iteration-specific data and state."""
        # ForEach doesn't need additional initialization beyond what base class provides

    def _get_current_item_value(self) -> Any:
        """Get the current iteration value."""
        if self._items and self._current_index < len(self._items):
            # Also set the index output
            self.parameter_output_values["index"] = self._current_index
            self.publish_update_to_parameter("index", self._current_index)
            return self._items[self._current_index]
        return None

    def _validate_iterative_connections(self) -> list[Exception]:
        """Validate ForEach-specific connections in addition to base validation."""
        errors = super()._validate_iterative_connections()

        # Check if items parameter has input connection
        if "items" not in self._connected_parameters:
            errors.append(
                Exception(
                    f"{self.name}: Missing required 'items' connection. "
                    "REQUIRED ACTION: Connect a data source (like Create List.output) to the ForEach Start 'items' input. "
                    "The ForEach Start needs a list of items to iterate through."
                )
            )

        return errors
