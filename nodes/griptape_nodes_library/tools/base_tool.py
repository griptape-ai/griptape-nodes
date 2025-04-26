from griptape.tools import BaseTool as GtBaseTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class BaseTool(DataNode):
    """Base tool node for creating Griptape tools.

    This node provides a generic implementation for initializing Griptape tools with configurable parameters.

    Attributes:
        off_prompt (bool): Indicates whether the tool should operate in off-prompt mode.
        tool (BaseTool): A dictionary representation of the created tool.
    """

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="tool",
                input_types=["Tool"],
                type="Tool",
                output_type="Tool",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="off_prompt",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="",
            )
        )

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = GtBaseTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
