from griptape.artifacts import ListArtifact
from griptape.tasks import PromptTask
from griptape.tools import WebScraperTool as GtWebScraperTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class WebScraper(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="url",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="",
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
        self.add_parameter(
            Parameter(
                name="tool",
                input_types=["Tool"],
                type="Tool",
                output_type="Tool",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="",
            )
        )

    def process(self) -> None:
        off_prompt = self.get_parameter_value("off_prompt")
        url = self.get_parameter_value("url")

        # Create the tool
        tool = GtWebScraperTool(off_prompt=off_prompt)
        scrape_task = PromptTask(
            tools=[tool],
            reflect_on_tool_use=False,
        )

        # Run the task
        output = ""
        response = scrape_task.run(url)
        if isinstance(response, ListArtifact):
            output += str(response[0].value[0].value)

        # Set the output
        self.parameter_output_values["output"] = output

        # Set the output
        self.parameter_output_values["tool"] = tool
