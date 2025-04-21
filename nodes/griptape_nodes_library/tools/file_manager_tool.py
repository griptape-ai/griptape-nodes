from griptape.tools import FileManagerTool as GtFileManagerTool

from griptape_nodes_library.tools.base_tool import BaseTool


class FileManager(BaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)

        # Create the tool
        tool = GtFileManagerTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
