from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.engines import PromptSummaryEngine
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Agent, Structure
from griptape.tasks import TextSummaryTask

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

    def _process(self, agent: Agent, prompt: BaseArtifact | str) -> Structure:
        include_details = self.get_parameter_value("include_details")

        args = [prompt] if prompt else []
        structure_id_stack = []
        active_structure_id = None
        for event in agent.run_stream(
            *args, event_types=[StartStructureRunEvent, TextChunkEvent, ActionChunkEvent, FinishStructureRunEvent]
        ):
            if isinstance(event, StartStructureRunEvent):
                active_structure_id = event.structure_id
                structure_id_stack.append(active_structure_id)
            if isinstance(event, FinishStructureRunEvent):
                structure_id_stack.pop()
                active_structure_id = structure_id_stack[-1] if structure_id_stack else None

            # If an Agent uses other Agents (via `StructureRunTool`), we will receive those events too.
            # We want to ignore those events and only show the events for this node's Agent.
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/984
            if agent.id == active_structure_id:
                # If the artifact is a TextChunkEvent, append it to the output parameter.
                if isinstance(event, TextChunkEvent):
                    self.append_value_to_parameter("output", value=event.token)
                    if include_details:
                        self.append_value_to_parameter("logs", value=event.token)

                # If the artifact is an ActionChunkEvent, append it to the logs parameter.
                if include_details and isinstance(event, ActionChunkEvent) and event.name:
                    self.append_value_to_parameter("logs", f"\n[Using tool {event.name}: ({event.path})]\n")

        return agent

    def process(self) -> Any:
        engine = PromptSummaryEngine(prompt_driver=self.create_driver())
        task = TextSummaryTask(summary_engine=engine)
        agent = Agent(tasks=[task])
        prompt = self.get_parameter_value("prompt")
        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            yield lambda: self._process(agent, prompt)

        # agent.run(self.get_parameter_value("prompt"))
        # self.parameter_output_values["output"] = agent.output
