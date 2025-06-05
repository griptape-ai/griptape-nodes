from typing import Any

from griptape.structures import Agent
from griptape.tools import CalculatorTool as GtCalculatorTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tasks.base_task import BaseTask


class Calculate(BaseTask):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                default_value=None,
                tooltip="URL to scrape",
                ui_options={"placeholder_text": "Enter something to calculate."},
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
                ui_options={"multiline": True, "placeholder_text": "Output from the calculator."},
            )
        )

    def process(self) -> Any:
        prompt = self.get_parameter_value("prompt")
        model = self.get_parameter_value("model")

        # Create the tool
        tool = GtCalculatorTool()

        # Run the task
        agent = Agent(tools=[tool], prompt_driver=self.create_driver(model=model))
        user_input = f"Give me the answer for: {prompt}\nOnly return the answer, no other text."

        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            yield lambda: self._process(agent, user_input)
