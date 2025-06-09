from griptape.tools import DateTimeTool as GtDateTimeTool

from griptape_nodes_library.tools.base_tool import BaseTool


class DateTime(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.update_tool_info(
            value="This DateTime tool can be given to an agent to help it perform date and time operations.",
            title="DateTime Tool",
        )
        self.hide_parameter_by_name("off_prompt")

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = GtDateTimeTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
