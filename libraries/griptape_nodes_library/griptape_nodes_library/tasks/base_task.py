from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class BaseTask(ControlNode):
    """Base task node for creating Griptape Tasks that can run on their own.

    Attributes:
        prompt (BaseTool): A dictionary representation of the created tool.
    """

    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata)
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
                name="output",
                type="str",
                output_type="str",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="The output of the task.",
                ui_options={"multiline": True, "placeholder_text": "Task output"},
            )
        )

    def create_driver(self) -> GriptapeCloudPromptDriver:
        return GriptapeCloudPromptDriver(
            model="gpt-4.1", api_key=self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR), stream=True
        )

    def process(self) -> None:
        # Create the task
        pass
