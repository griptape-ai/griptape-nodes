from typing import Any

from griptape.structures import Agent, Structure
from griptape.tools import DateTimeTool as GtDateTimeTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tasks.base_task import BaseTask

FORMAT_CHOICES = [
    "2024-06-15",
    "2024-06-15 12:00:00",
    "Jun 15, 2024",
    "Friday, June 15 at 2pm",
    "June 18th, 2024, in the afternoon",
    "This Saturday at 7 PM",
    "Custom format",
]


class DateAndTime(BaseTask):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                default_value=None,
                tooltip="Date and time information to get",
                ui_options={"placeholder_text": "Enter something to get the date and time for."},
            )
        )
        self.add_parameter(
            Parameter(
                name="format",
                type="str",
                default_value=FORMAT_CHOICES[2],
                tooltip="The format to use for the date and time.",
                traits={Options(choices=FORMAT_CHOICES)},
                ui_options={"hide": False},
            )
        )
        self.add_parameter(
            Parameter(
                name="custom_format",
                type="str",
                default_value="",
                tooltip="The custom format to use for the date and time.",
                ui_options={"hide": True, "placeholder_text": "any custom format"},
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
                ui_options={"multiline": True, "placeholder_text": "The resulting date and time."},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "format":
            if "Custom" in value:
                self.show_parameter_by_name("custom_format")
            else:
                self.hide_parameter_by_name("custom_format")
        return super().after_value_set(parameter, value)

    def process(self) -> AsyncResult[Structure]:
        prompt = self.get_parameter_value("prompt")
        model = self.get_parameter_value("model")
        date_format = self.get_parameter_value("format")
        if date_format == "Custom format":
            date_format = self.get_parameter_value("custom_format")

        # Create the tool
        tool = GtDateTimeTool()

        # Run the task
        agent = Agent(tools=[tool], prompt_driver=self.create_driver(model=model))
        user_input = f"Get date and time information for: {prompt}\n in the following format: {date_format}\nOnly return the answer, no other text."

        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            yield lambda: self._process(agent, user_input)
