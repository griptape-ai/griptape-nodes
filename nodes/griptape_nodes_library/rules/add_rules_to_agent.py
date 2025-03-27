from griptape.drivers.prompt.griptape_cloud import (
    GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver,
)
from griptape.structures import Agent as gtAgent
from griptape.utils import Stream

from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class AddRulesetToAgent(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="agent",
                allowed_types=["Agent"],
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="rulesets",
                allowed_types=["Ruleset"],
                tooltip="",
                allowed_modes={ParameterMode.INPUT},
            )
        )
    def process(self) -> None:
        # Get input values
        params = self.parameter_values
        agent_dict = params.get("agent", None)
        ruleset = params.get("rulesets", None)

        print ("Trying to add rulesets to agent:")

        if not agent_dict:
            prompt_driver = GtGriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.getkey(value=f"env.{SERVICE}.{API_KEY_ENV_VAR}"),
                stream=True,
            )
            if ruleset:
            agent = gtAgent(prompt_driver=prompt_driver, rulesets=[ruleset])
        
        else:
            current_agent_ruleset = agent_dict.get("rulesets", None)
            print(current_agent_ruleset)


        # agent = gtAgent().from_dict(agent_dict)

        # # Add rules to the agent

        # self.parameter_output_values["agent"] = agent.to_dict()
