from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Agent, Structure

from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class BaseTask(ControlNode):
    """Base task node for creating Griptape Tasks that can run on their own."""

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata)

    def create_driver(self, model: str = "gpt-4.1") -> GriptapeCloudPromptDriver:
        return GriptapeCloudPromptDriver(
            model=model,
            api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
            stream=True,
        )

    def _process(self, agent: Agent, prompt: BaseArtifact | str) -> Structure:
        args = [prompt] if prompt else []
        for event in agent.run_stream(
            *args, event_types=[StartStructureRunEvent, TextChunkEvent, ActionChunkEvent, FinishStructureRunEvent]
        ):
            if isinstance(event, TextChunkEvent):
                self.append_value_to_parameter("output", value=event.token)

        return agent

    def process(self) -> AsyncResult[Structure]:
        # Base implementation returns an empty Agent
        def _process() -> Structure:
            return Agent()

        yield _process
