from griptape.drivers.prompt.griptape_cloud import (
    GriptapeCloudPromptDriver
)
from griptape.structures import Agent
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
    ParameterUIOptions,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class BaseAgentNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.config = GriptapeNodes.ConfigManager()

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent"],
                tooltip="Use an existing agent. If not specified, will automatically create one.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt_driver",
                type="PromptDriver",
                input_types=["PromptDriver"],
                default_value=None,
                tooltip="Connect a prompt driver to use. If not specified, will use the default OpenAI gpt-4o.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        with ParameterGroup(group_name="Agent Abilities") as agent_abilities_group:
            self.add_parameter(
                Parameter(
                    name="tools",
                    input_types=["list[Tool]", "Tool"],
                    default_value=None,
                    tooltip="",
                    allowed_modes={ParameterMode.INPUT},
                )
            )
            self.add_parameter(
                Parameter(
                    name="rulesets",
                    input_types=["list[Ruleset]", "Ruleset"],
                    tooltip="Rulesets to apply to the agent to control its behavior.",
                    allowed_modes={ParameterMode.INPUT},
                )
            )
        self.add_parameter(
            Parameter(
                name="prompt",
                type="str",
                default_value="",
                tooltip="The prompt to call an agent",
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                        placeholder_text="The prompt to call an agent",
                    )
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )


        with ParameterGroup(group_name="Agent Response") as agent_response_group:
            self.add_parameter(
                Parameter(
                    name="agent_response",
                    type="str",
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

    def validate_node(self) -> list[Exception] | None:
        # All env values are stored in the SecretsManager. Check if they exist using this method.
        exceptions = []
        try:
            api_key = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

            if not api_key:
                raise ValueError(f"API key for {SERVICE} is not set.")
        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)
            return exceptions
        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def getkey(self, value: str) -> str:
        key = self.config.get_config_value(f"nodes.{value}")
        return key

    def get_default_prompt_driver(self) -> GriptapeCloudPromptDriver:
        return GriptapeCloudPromptDriver(
            model="gpt-4o",
            api_key=self.getkey(value=f"{SERVICE}.{API_KEY_ENV_VAR}"),
            stream=True,
        )

    def is_stream(self, agent: Agent) -> bool:
        if agent and agent.tasks:
            task = agent.tasks[0]
            if isinstance(task, PromptTask):
                prompt_driver = task.prompt_driver
                return prompt_driver.stream
            return False
        return False

    def process(self) -> None:
        pass
