from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver

from griptape_nodes.exe_types.node_types import ControlNode

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class BaseTask(ControlNode):
    """Base task node for creating Griptape Tasks that can run on their own."""

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata)

    def create_driver(self, model: str = "gpt-4.1") -> GriptapeCloudPromptDriver:
        return GriptapeCloudPromptDriver(
            model=model, api_key=self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR), stream=True
        )

    def process(self) -> None:
        # Create the task
        pass
