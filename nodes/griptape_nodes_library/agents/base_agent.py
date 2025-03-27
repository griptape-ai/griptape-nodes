from griptape.drivers.prompt.griptape_cloud import (
    GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver,
)
from griptape.structures import Agent as gtAgent
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
    ParameterUIOptions,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class BaseAgent(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.config = GriptapeNodes.ConfigManager()

        self.category = "Agent"
        self.description = "Create an agent and run it."
        self.add_parameter(
            Parameter(
                name="agent",
                allowed_types=["Agent"],
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_driver",
                allowed_types=["BasePromptDriver"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="tool_list",
                allowed_types=["list[BaseTool]"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="behaviorruleset",
                allowed_types=["Ruleset"],
                tooltip="",
                allowed_modes={ParameterMode.INPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                allowed_types=["str"],
                default_value="",
                tooltip="",
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                    )
                ),
            )
        )

        self.add_parameter(
            Parameter(
                name="agent_response",
                allowed_types=["str"],
                default_value="",
                tooltip="What the agent said.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                        placeholder_text="The agent will respond here. Connect the output to other nodes.",
                    )
                ),
            )
        )

    def getkey(self, value: str) -> str:
        key = self.config.get_config_value(value)
        return key

    def get_default_prompt_driver(self) -> GtGriptapeCloudPromptDriver:
        return GtGriptapeCloudPromptDriver(
            model="gpt-4o",
            api_key=self.getkey(value=f"env.{SERVICE}.{API_KEY_ENV_VAR}"),
            stream=True,
        )

    def is_stream(self, agent: gtAgent) -> bool:
        if agent:
            prompt_driver = agent.tasks[0].prompt_driver
            return prompt_driver.stream

    def process(self) -> None:
        pass
