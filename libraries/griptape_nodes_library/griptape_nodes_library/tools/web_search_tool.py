from typing import Any

from griptape.drivers import DuckDuckGoWebSearchDriver, ExaWebSearchDriver, GoogleWebSearchDriver
from griptape.tools import WebSearchTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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
                allowed_modes={ParameterMode.PROPERTY},
            )
        )
        self.add_node_element(
            ParameterMessage(
                name="api_keys_message",
                value="Please ensure you have set appropriate API keys for the selected search engine.",
                variant="warning",
                title="API Keys",
                ui_options={"hide": True},
            )
        )
        self.move_element_to_position("tool", position="last")
        self.hide_parameter_by_name("off_prompt")

    def _duck_duck_go_driver(self) -> DuckDuckGoWebSearchDriver:
        return DuckDuckGoWebSearchDriver()

    def _google_driver(self) -> GoogleWebSearchDriver:
        return GoogleWebSearchDriver(
            api_key=GriptapeNodes.SecretsManager().get_secret("GOOGLE_API_KEY"),
            search_id=GriptapeNodes.SecretsManager().get_secret("GOOGLE_API_SEARCH_ID"),
        )

    def _exa_driver(self) -> ExaWebSearchDriver:
        return ExaWebSearchDriver(
            api_key=GriptapeNodes.SecretsManager().get_secret("EXA_API_KEY"),
        )

    def check_api_keys(self) -> bool:
        search_engine = self.get_parameter_value("search_engine")
        api_keys = SEARCH_ENGINE_MAP[search_engine]["api_keys"]
        if api_keys is None:
            return True
        for api_key in api_keys:
            if not GriptapeNodes.SecretsManager().get_secret(api_key):
                return False
        return True

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "search_engine":
            if value == "DuckDuckGo":
                self.hide_message_by_name("api_keys_message")
            else:
                api_key_message = self.get_message_by_name_or_element_id("api_keys_message")
                if api_key_message:
                    api_key_message.value = (
                        f"{value} requires the following API keys: {SEARCH_ENGINE_MAP[value]['api_keys']}"
                    )
                if not self.check_api_keys():
                    self.show_message_by_name("api_keys_message")
                else:
                    self.hide_message_by_name("api_keys_message")
        super().after_value_set(parameter, value)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        if not self.check_api_keys():
            return [ValueError("Please ensure you have set appropriate API keys for the selected search engine.")]
        return None

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

        # Set the output
        self.parameter_output_values["tool"] = tool
