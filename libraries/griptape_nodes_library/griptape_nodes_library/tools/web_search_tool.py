from griptape.drivers import DuckDuckGoWebSearchDriver, ExaWebSearchDriver, GoogleWebSearchDriver
from griptape.tools import WebSearchTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tools.base_tool import BaseTool

SEARCH_ENGINE_MAP = {
    "DuckDuckGo": {
        "api_keys": None,
    },
    "Google": {
        "api_keys": ["GOOGLE_API_KEY", "GOOGLE_API_SEARCH_ID"],
    },
    "Exa": {
        "api_keys": ["EXA_API_KEY"],
    },
}
SEARCH_ENGINES = list(SEARCH_ENGINE_MAP.keys())


class WebSearch(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.update_tool_info(
            value="The WebSearch tool can be given to an agent to help search the web.\n\nIt uses DuckDuckGo by default, but can be configured to use other search engines with their API keys.",
            title="WebSearch Tool",
        )
        self.add_parameter(
            Parameter(
                name="search_engine",
                type="str",
                tooltip="The search engine to use.",
                default_value=SEARCH_ENGINES[0],
                traits={Options(choices=SEARCH_ENGINES)},
            )
        )
        self.swap_parameters("search_engine", "tool")
        self.hide_parameter_by_name("off_prompt")

    def _duck_duck_go_driver(self) -> DuckDuckGoWebSearchDriver:
        return DuckDuckGoWebSearchDriver()

    def _google_driver(self) -> GoogleWebSearchDriver:
        return GoogleWebSearchDriver(
            api_key=self.get_config_value(service="GOOGLE", value="GOOGLE_API_KEY"),
            search_id=self.get_config_value(service="GOOGLE", value="GOOGLE_API_SEARCH_ID"),
        )

    def _exa_driver(self) -> ExaWebSearchDriver:
        return ExaWebSearchDriver(
            api_key=self.get_config_value(service="EXA", value="EXA_API_KEY"),
        )

    def process(self) -> None:
        off_prompt = self.get_parameter_value("off_prompt")
        search_engine = self.get_parameter_value("search_engine")

        if search_engine == "DuckDuckGo":
            driver = self._duck_duck_go_driver()
        elif search_engine == "Google":
            driver = self._google_driver()
        elif search_engine == "Exa":
            driver = self._exa_driver()
        else:
            msg = f"Invalid search engine: {search_engine}"
            raise ValueError(msg)

        # Create the tool
        tool = WebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

        logger.info(f"WebSearchTool created: {tool}")
        # Set the output
        self.parameter_output_values["tool"] = tool
