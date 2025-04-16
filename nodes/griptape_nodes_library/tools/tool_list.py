from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class ToolList(DataNode):
    """Combine tools to give an agent a more complex set of tools."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add a parameter for a list of tools
        self.add_parameter(
            Parameter(
                name="tool_1",
                input_types=["Tool"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Tool to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="tool_2",
                input_types=["Tool"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Tool to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="tool_3",
                input_types=["Tool"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Tool to add to the list",
            )
        )
        self.add_parameter(
            Parameter(
                name="tool_4",
                input_types=["Tool"],
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
                tooltip="Tool to add to the list",
            )
        )

        # Add output parameter for the combined tool list
        self.add_parameter(
            Parameter(
                name="tool_list",
                output_type="list[Tool]",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=None,
                tooltip="Combined list of tools",
            )
        )

    def process(self) -> None:
        """Process the node by combining tools into a list."""
        # Get the input tools
        tool_1 = self.parameter_values.get("tool_1", None)
        tool_2 = self.parameter_values.get("tool_2", None)
        tool_3 = self.parameter_values.get("tool_3", None)
        tool_4 = self.parameter_values.get("tool_4", None)

        # Combine the tools into a list
        tools = [tool for tool in [tool_1, tool_2, tool_3, tool_4] if tool is not None]

        # Set output values
        self.parameter_output_values["tool_list"] = tools
