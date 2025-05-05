from griptape.drivers import DuckDuckGoWebSearchDriver
from griptape.tools import WebSearchTool as GtWebSearchTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.tools.base_tool import BaseTool


class WebSearch(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="web_search_config",
                input_types=["Web Search Driver"],
                type="Web Search Driver",
                default_value={},
                tooltip="",
                allowed_modes={ParameterMode.INPUT},
            )
        )

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)

        driver = self.parameter_values.get("web_search_config", DuckDuckGoWebSearchDriver())

        # Create the tool
        tool = GtWebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool
