from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.parameter_events import AlterElementEvent


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
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if not list_values or not isinstance(list_values, list):
            return
        # Remove any existing dynamically created output parameters
        # Create a new output parameter for each item in the list
        for i, item in enumerate(list_values):
            # Determine the type of the item
            item_type = self._determine_item_type(item)
            # Create a new output parameter with the appropriate type
            if i >= len(self.dynamic_params):
                output_param = Parameter(
                    name=f"item_{i}",
                    tooltip=f"Item {i} from the input list",
                    output_type=item_type,
                    allowed_modes={ParameterMode.OUTPUT},
                )
                self.add_parameter(output_param)
                self.dynamic_params.append(output_param)
            else:
                output_param = self.dynamic_params[i]
                output_param.output_type = item_type

            modified_request = AlterElementEvent(element_details=output_param.to_event(self))
            EventBus.publish_event(ExecutionGriptapeNodeEvent(ExecutionEvent(payload=modified_request)))
            # Set the value of the output parameter
            self.parameter_output_values[f"item_{i}"] = item

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
