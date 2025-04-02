from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


class ToolListNode(ControlNode):
    """Combine tools to give an agent a more complex set of tools."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of tools
        self.add_parameter(
            Parameter(
                name="tools",
                input_types=["list[object]"],
                allowed_modes={ParameterMode.INPUT},
                default_value=[],
                tooltip="List of tools to combine",
            )
        )

        # Add output parameter for the combined tool list
        self.add_parameter(
            Parameter(
                name="tool_list",
                output_type="list[object]",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=[],
                tooltip="Combined list of tools",
            )
        )

    def process(self) -> None:
        """Process the node by combining tools into a list."""
        # Get the input tools
        input_tools = self.parameter_values.get("tools", [])

        # Ensure it's a list
        if not isinstance(input_tools, list):
            input_tools = [input_tools] if input_tools is not None else []

        # Flatten nested lists if needed (in case tools come in as lists)
        tool_list = []
        for item in input_tools:
            if isinstance(item, list):
                # Add each tool from the list
                tool_list.extend(item)
            elif item is not None:
                # Add single tool
                tool_list.append(item)

        # Set output values
        self.parameter_output_values["tool_list"] = tool_list
        self.parameter_values["tool_list"] = tool_list  # For get_value compatibility
