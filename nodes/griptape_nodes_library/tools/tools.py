from griptape.drivers import DuckDuckGoWebSearchDriver
from griptape.tools import BaseTool, CalculatorTool, DateTimeTool, WebSearchTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode


class gnBaseTool(DataNode):
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
                name="off_prompt",
                allowed_types=["bool"],
                default_value=False,
                tooltip="",
            )
        )
        self.add_parameter(Parameter(name="tool", allowed_types=["BaseTool"], default_value=None, tooltip=""))

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = BaseTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool


class gnCalculatorTool(gnBaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = CalculatorTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool


class gnDateTimeTool(gnBaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = DateTimeTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool


class gnWebSearchTool(gnBaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="driver",
                allowed_types=["WebSearchDriver"],
                default_value={},
                tooltip="",
            )
        )

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)
        driver = self.parameter_values.get("driver", None)
        if not driver:
            driver = DuckDuckGoWebSearchDriver()

        # Create the tool
        tool = WebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool
