from griptape.artifacts import ListArtifact
from griptape.structures import Agent, Structure
from griptape.tasks import PromptTask
from griptape.tools import WebScraperTool as GtWebScraperTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tasks.base_task import BaseTask


class ScrapeWeb(BaseTask):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                default_value=None,
                tooltip="URL to scrape",
                ui_options={"placeholder_text": "Enter the URL to scrape."},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                default_value="gpt-4.1-mini",
                tooltip="The model to use for the task.",
                traits={Options(choices=["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-5"])},
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
                ui_options={"multiline": True, "placeholder_text": "Output from the web scraper."},
            )
        )

    def process(self) -> AsyncResult[Structure]:
        prompt = self.get_parameter_value("prompt")
        model = self.get_parameter_value("model")

        # Create the tool
        tool = GtWebScraperTool()
        scrape_task = PromptTask(
            tools=[tool],
            reflect_on_tool_use=False,
            prompt_driver=self.create_driver(model=model),
        )

        def _process() -> Structure:
            # Run the task
            output = ""
            response = scrape_task.run(f"Scrape the web for information about: {prompt}")
            if isinstance(response, ListArtifact):
                output += str(response[0].value[0].value)

            # Set the output
            self.parameter_output_values["output"] = output
            return Agent()  # Return a proper Structure instance

        yield _process
