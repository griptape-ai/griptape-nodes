from griptape.tools import CalculatorTool as GtCalculatorTool

from griptape_nodes_library.tools.base_tool import BaseTool


class Calculator(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.update_tool_info(
            value="This calculator tool can be given to an agent to help it perform calculations.",
            title="Calculator Tool",
        )
        self.hide_parameter_by_name("off_prompt")

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)

        # Create the tool
        tool = GtCalculatorTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
