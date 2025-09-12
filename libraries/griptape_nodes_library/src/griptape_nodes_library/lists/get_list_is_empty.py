from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class GetListIsEmpty(ControlNode):
    """GetListIsEmpty Node that that checks if a list is empty."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)
        self.is_empty = Parameter(
            name="is_empty",
            tooltip="Output if the list is empty",
            output_type="bool",
            default_value=True,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.is_empty)

    def _is_empty(self) -> bool:
        list_items = self.get_parameter_value("items")
        return not list_items or len(list_items) == 0

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "items":
            is_empty = self._is_empty()
            self.parameter_output_values["is_empty"] = is_empty
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            is_empty = self._is_empty()
            self.parameter_output_values["is_empty"] = is_empty
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "items":
            self.parameter_output_values["is_empty"] = True
            self.publish_update_to_parameter("is_empty", True)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> None:
        # Get the list of items from the input parameter
        is_empty = self._is_empty()

        self.parameter_output_values["is_empty"] = is_empty
