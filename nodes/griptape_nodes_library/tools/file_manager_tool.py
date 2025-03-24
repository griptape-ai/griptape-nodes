from griptape.tools import FileManagerTool

from griptape_nodes_library.tools.tools import gnBaseTool


class gnFileManagerTool(gnBaseTool):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)

        # Create the tool
        tool = FileManagerTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
