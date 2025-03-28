from griptape.drivers.prompt.griptape_cloud import (
    GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver,
)
from griptape.structures import Agent as gtAgent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class AddRulesetToAgent(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.config = GriptapeNodes.ConfigManager()
        self.logger = GriptapeNodes.get_logger()
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

    def getkey(self, value: str) -> str:
        key = self.config.get_config_value(value)
        return key

    def process(self) -> None:
        # Get input values
        params = self.parameter_values
        agent_dict = params.get("agent", None)
        ruleset = params.get("rulesets", None)

        self.logger.info("Trying to add rulesets to agent:")

        if not agent_dict:
            prompt_driver = GtGriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.getkey(value=f"env.{SERVICE}.{API_KEY_ENV_VAR}"),
                stream=True,
            )
            if ruleset:
                agent_dict = gtAgent(prompt_driver=prompt_driver, rulesets=[ruleset]).to_dict()
            else:
                agent_dict = gtAgent(prompt_driver=prompt_driver).to_dict()   

        else:
            current_agent_ruleset = agent_dict.get("rulesets", [])
            self.logger.info(current_agent_ruleset)
            new_agent_ruleset = ruleset.to_dict()
            self.logger.info(new_agent_ruleset)
            current_agent_ruleset.extend(new_agent_ruleset)

            agent_dict["rulesets"] = current_agent_ruleset
        
        self.parameter_output_values["agent"] = agent_dict
