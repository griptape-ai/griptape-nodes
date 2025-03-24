from griptape.rules import Rule, Ruleset
from griptape.tools import RagTool

from griptape_nodes_library.tools.tools import gnBaseTool


class gnRagTool(gnBaseTool):
    def process(self) -> None:
        description = self.parameter_values.get("description", "Contains information.")
        off_prompt = self.parameter_values.get("off_prompt", False)
        rag_engine = self.parameter_values.get("rag_engine", None)

        # Create the tool
        tool = RagTool(description=description, off_prompt=off_prompt, rag_engine=rag_engine)

        # Create ruleset
        ruleset = Ruleset(
            name="GriptapeRagToolWithRules",
            rules=[
                Rule("Mandatory: Include all provided footnotes in your response, without exception."),
                Rule("Use the RAG Tool to get answers to your questions."),
            ],
        )

        # Set the outputs
        self.parameter_output_values["tool"] = tool
        self.parameter_output_values["rules"] = ruleset
