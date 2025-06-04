from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.engines import PromptSummaryEngine
from griptape.events import TextChunkEvent
from griptape.structures import Agent, Structure
from griptape.tasks import TextSummaryTask
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tasks.base_task import BaseTask

SERVICE = "griptape_cloud"
API_KEY_ENV_VAR = "GriptapeCloudApiKey"


class SummarizeText(BaseTask):
    """Base task node for creating Griptape Tasks that can run on their own.

    Attributes:
        prompt (BaseTool): A dictionary representation of the created tool.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="",
                ui_options={"multiline": True, "placeholder_text": "Input text to process"},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                default_value="gpt-4.1-mini",
                tooltip="The model to use for the task.",
                traits={Options(choices=["gpt-4.1", "gpt-4.1-preview", "gpt-4.1-mini", "gpt-4.1-mini-preview"])},
                ui_options={"hidden": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                output_type="str",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The output of the task.",
                ui_options={"multiline": True, "placeholder_text": "Task output"},
            )
        )

    def _process(self, agent: Agent, prompt: BaseArtifact | str) -> Structure:
        args = [prompt] if prompt else []
        for artifact in Stream(agent).run(args):
            if isinstance(artifact, TextChunkEvent):
                self.append_value_to_parameter("output", value=artifact.token)
        return agent

    def process(self) -> Any:
        engine = PromptSummaryEngine(prompt_driver=self.create_driver())
        task = TextSummaryTask(summary_engine=engine)
        agent = Agent(tasks=[task])
        prompt = self.get_parameter_value("prompt")
        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            yield lambda: self._process(agent, prompt)
