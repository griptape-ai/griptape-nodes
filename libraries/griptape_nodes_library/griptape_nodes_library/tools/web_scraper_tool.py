from typing import Any

from griptape.tools import WebScraperTool as GtWebScraperTool

from griptape_nodes_library.tools.base_tool import BaseTool


class WebScraper(BaseTool):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        # Create the tool
        tool = GtWebScraperTool(off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
