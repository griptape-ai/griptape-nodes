from griptape.drivers import DuckDuckGoWebSearchDriver, ExaWebSearchDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent, Structure
from griptape.tasks import PromptTask
from griptape.tools import WebSearchTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tasks.base_task import BaseTask


class SearchWeb(BaseTask):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                default_value=None,
                tooltip="Search the web for information",
                ui_options={"placeholder_text": "Enter the search query."},
            )
        )
        self.add_parameter(
            Parameter(
                name="summarize",
                type="bool",
                default_value=False,
                tooltip="Summarize the results",
                ui_options={"hide": False},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                default_value="gpt-4.1-mini",
                tooltip="The model to use for the task.",
                traits={Options(choices=["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"])},
                ui_options={"hide": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="",
                ui_options={"multiline": True, "placeholder_text": "Output from the web search."},
            )
        )

    def process(self) -> AsyncResult[Structure]:
        prompt = self.get_parameter_value("prompt")
        exa_driver = ExaWebSearchDriver(api_key=self.get_config_value(service="EXA", value="EXA_API_KEY"))
        duckduckgo_driver = DuckDuckGoWebSearchDriver()
        # Create the tool
        tool = WebSearchTool(web_search_driver=exa_driver)
        task = PromptTask(
            tools=[tool],
            reflect_on_tool_use=self.get_parameter_value("summarize"),
            prompt_driver=GriptapeCloudPromptDriver(model=self.get_parameter_value("model"), stream=True),
        )

        agent = Agent(tasks=[task])
        # Run the task
        user_input = f"Search the web for {prompt}"
        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            yield lambda: self._process(agent, user_input)

        self.parameter_output_values["output"] = str(agent.output)
