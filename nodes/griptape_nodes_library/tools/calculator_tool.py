from griptape.tools import CalculatorTool

from griptape_nodes_library.tools.tools import BaseToolNode


class CalculatorToolNode(BaseToolNode):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)

        # Create the tool
        tool = CalculatorTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
