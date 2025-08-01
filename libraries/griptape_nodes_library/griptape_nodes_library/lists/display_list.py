from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class DisplayList(ControlNode):
    """DisplayList Node that takes a list and creates output parameters for each item in the list.

    This node takes a list as input and creates a new output parameter for each item in the list,
    with the type of the object in the list. This allows for dynamic output parameters based on
    the content of the input list.
    """

    dynamic_params: list[Parameter]

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)
        self.dynamic_params = []
        # We'll create output parameters dynamically during processing

    def process(self) -> None:
        # Update the display list based on current input
        self._update_display_list()

    def _update_display_list(self) -> None:
        """Update the display list parameters based on current input values."""
        # Clear all dynamically-created parameters at the start
        self._clear_dynamic_parameters()

        # Try to get the list of items from the input parameter
        try:
            list_values = self.get_parameter_value("items")
        except Exception:
            # If we can't get the parameter value (e.g., connected node not resolved yet),
            # just clear and return - we'll update again when values are available
            return

        if not list_values or not isinstance(list_values, list):
            return

        # Regenerate parameters for each item in the list
        for i, item in enumerate(list_values):
            # Determine the type of the item
            item_type = self._determine_item_type(item)

            # Create a new output parameter with the appropriate type
            output_param = Parameter(
                name=f"item_{i}",
                tooltip=f"Item {i} from the input list",
                output_type=item_type,
                allowed_modes={ParameterMode.OUTPUT},
            )
            self.add_parameter(output_param)
            self.dynamic_params.append(output_param)

            # Set the value of the output parameter
            self.parameter_output_values[f"item_{i}"] = item

    def _clear_dynamic_parameters(self) -> None:
        """Clear all dynamically-created parameters from the node."""
        for param in self.dynamic_params:
            # Remove the parameter's output value first
            if param.name in self.parameter_output_values:
                del self.parameter_output_values[param.name]
            # Then remove the parameter element
            self.remove_parameter_element(param)
        self.dynamic_params.clear()

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
            return "ImageArtifact"
        return ParameterTypeBuiltin.ANY.value

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Update display list when an incoming connection is made."""
        # Only update if the connection is to our items parameter
        if target_parameter == self.items_list:
            self._update_display_list()
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Update display list when an incoming connection is removed."""
        # Only update if the connection was to our items parameter
        if target_parameter == self.items_list:
            self._update_display_list()
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update display list when a value is assigned to the items parameter."""
        # Only update if the value was set on our items parameter
        if parameter == self.items_list:
            self._update_display_list()
        return super().after_value_set(parameter, value)
