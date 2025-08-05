import contextlib
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class DisplayList(ControlNode):
    """DisplayList Node that takes a list and creates output parameters for each item in the list.

    This node takes a list as input and creates a new output parameter for each item in the list,
    with the type of the object in the list. This allows for dynamic output parameters based on
    the content of the input list.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            output_type="list",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.items)
        # Spot that will display the list.
        self.items_list = ParameterList(
            name="display_list",
            tooltip="Output list",
            type=ParameterTypeBuiltin.ANY.value,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide": True},
        )
        self.add_parameter(self.items_list)
        # Track whether we're already updating to prevent duplicate calls
        self._updating_display_list = False
        # We'll create output parameters dynamically during processing

    def process(self) -> None:
        # The display list is already updated by after_value_set when the items parameter changes
        # No need to update it again during process() - this prevents duplicate processing
        logger.info(
            "DisplayList.process(): Display list already updated by after_value_set, no additional processing needed for node %s",
            self.name,
        )

    def _update_display_list(self) -> None:
        """Update the display list parameters based on current input values."""
        # Prevent duplicate calls
        if self._updating_display_list:
            logger.info(
                "DisplayList._update_display_list(): Already updating for node %s, skipping duplicate call",
                self.name,
            )
            return

        self._updating_display_list = True
        logger.info("DisplayList._update_display_list(): Starting display list update for node %s", self.name)

        try:
            # Clear all dynamically-created parameters at the start
            self._clear_list()

            # Try to get the list of items from the input parameter
            try:
                list_values = self.get_parameter_value("items")
            except Exception:
                # If we can't get the parameter value (e.g., connected node not resolved yet),
                # just clear and return - we'll update again when values are available
                return

            # Prepare ui_options update in one go to avoid multiple change events
            new_ui_options = self.items_list.ui_options.copy()

            if not list_values or not isinstance(list_values, list):
                new_ui_options["hide"] = True
                if "display" in new_ui_options:
                    del new_ui_options["display"]
                self.items_list.ui_options = new_ui_options
                return

            # Regenerate parameters for each item in the list
            if len(list_values) < 1:
                new_ui_options["hide"] = True
                self.items_list.ui_options = new_ui_options
                return

            new_ui_options["hide"] = False
            item_type = self._determine_item_type(list_values[0])

            if item_type == "ImageUrlArtifact":
                new_ui_options["display"] = "grid"

            # Apply both changes first
            self.items_list.type = item_type
            self.items_list.ui_options = new_ui_options

            # Create child parameters and ensure they're properly tracked
            for item in list_values:
                new_child = self.items_list.add_child_parameter()
                # Set the parameter value without emitting immediate change events
                self.set_parameter_value(new_child.name, item, emit_change=False)
                # Ensure the new child parameter is tracked for flush events
                if hasattr(self, "_tracked_parameters") and new_child not in self._tracked_parameters:
                    self._tracked_parameters.append(new_child)
        finally:
            self._updating_display_list = False
            logger.info("DisplayList._update_display_list(): Completed display list update for node %s", self.name)

    def _clear_list(self) -> None:
        """Clear all dynamically-created parameters from the node."""
        # Clear any tracked parameters to prevent stale tracking between runs
        if hasattr(self, "_tracked_parameters"):
            # Remove any child parameters of items_list from tracking
            for child in self.items_list.find_elements_by_type(Parameter):
                if child in self._tracked_parameters:
                    self._tracked_parameters.remove(child)

        for child in self.items_list.find_elements_by_type(Parameter):
            # Remove the parameter value - this will also handle parameter_output_values
            with contextlib.suppress(KeyError):
                self.remove_parameter_value(child.name)
            # Remove the parameter from the list
        self.items_list.clear_list()

        # Also clear the items_list from tracking to ensure clean state
        if hasattr(self, "_tracked_parameters") and self.items_list in self._tracked_parameters:
            self._tracked_parameters.remove(self.items_list)

    def _determine_item_type(self, item: Any) -> str:
        """Determine the type of an item for parameter type assignment."""
        if isinstance(item, str):
            return ParameterTypeBuiltin.STR.value
        if isinstance(item, bool):
            return ParameterTypeBuiltin.BOOL.value
        if isinstance(item, int):
            return ParameterTypeBuiltin.INT.value
        if isinstance(item, float):
            return ParameterTypeBuiltin.FLOAT.value
        if isinstance(item, (ImageUrlArtifact, ImageArtifact)):
            return "ImageUrlArtifact"
        return ParameterTypeBuiltin.ANY.value

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update display list when a value is assigned to the items parameter."""
        # Only update if the value was set on our items parameter
        if parameter == self.items:
            logger.info(
                f"DisplayList.after_value_set(): Items parameter updated for node {self.name}, triggering display list update"
            )
            self._update_display_list()
        return super().after_value_set(parameter, value)
