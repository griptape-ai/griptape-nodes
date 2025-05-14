from griptape.engines import PromptSummaryEngine
from griptape.tools import PromptSummaryTool as GtPromptSummaryTool

from griptape_nodes_library.tools.base_tool import BaseTool


class PromptSummary(BaseTool):
    """A tool generator class that creates a configured PromptSummaryTool.

    This class extends BaseTool to create a tool specifically for summarizing text.
    It configures a PromptSummaryEngine with an optional prompt driver and wraps it
    in a PromptSummaryTool.
    """

    def process(self) -> None:
        """Process method that creates and configures the PromptSummaryTool.

        This method:
        1. Gets the prompt_driver from parameter_values (or uses default if none)
        2. Creates a PromptSummaryEngine with the prompt driver
        3. Creates a PromptSummaryTool with the engine
        4. Outputs the tool as a dictionary for later use
        """
        # Get the prompt driver from parameters, will be None if not provided
        prompt_driver = self.parameter_values.get("prompt_driver", None)

        if prompt_driver is None:
            msg = "Prompt driver is required for PromptSummaryTool."
            raise ValueError(msg)

        # Create the engine with the prompt driver (engine handles the summarization logic)
        engine = PromptSummaryEngine(prompt_driver=prompt_driver)

        # Create the tool with the engine (tool provides the interface for using the engine)
        tool = GtPromptSummaryTool(prompt_summary_engine=engine)

        # Store the tool as a dictionary in the output parameters for later use
        self.parameter_output_values["tool"] = tool
