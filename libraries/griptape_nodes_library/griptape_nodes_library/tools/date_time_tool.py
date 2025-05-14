from griptape.tools import DateTimeTool as GtDateTimeTool

from griptape_nodes_library.tools.base_tool import BaseTool


class DateTime(BaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = GtDateTimeTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
