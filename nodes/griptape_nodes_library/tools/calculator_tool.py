from griptape.tools import CalculatorTool as GtCalculatorTool

from griptape_nodes_library.tools.base_tool import BaseTool


class Calculator(BaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)

        # Create the tool
        tool = GtCalculatorTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
