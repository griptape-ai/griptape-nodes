from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class ListTexts(DataNode):
    """Create a list of strings from multiple input values, and immediately forwards to output."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Single parameter for both input and output
        self.add_parameter(
            Parameter(
                name="string_list",
                allowed_modes={
                    ParameterMode.INPUT,
                    ParameterMode.OUTPUT,
                    ParameterMode.PROPERTY,
                },
                input_types=[
                    "str",
                    "list[str]",
                    "list",
                ],
                type="list[str]",
                output_type="list[str]",
                default_value=[],
                tooltip="The list of strings",
            )
        )

    # Override process to make it a no-op passthrough
    def process(self) -> None:
        """Pass through the input values directly to output."""
        # Get the input values
        inputs = self.parameter_values.get("string_list", [])

        # Make sure we have a list
        if not isinstance(inputs, list):
            inputs = [str(inputs)] if inputs is not None else []

        # Values are already stored in parameter_values, just copy to output values
        self.parameter_output_values["string_list"] = inputs
        self.parameter_values["string_list"] = inputs
