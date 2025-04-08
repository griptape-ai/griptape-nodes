from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes_library.agents.create_agent import CreateAgent

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class RunAgent(CreateAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Remove unused inputs
        param = self.get_parameter_by_name("rulesets")
        if param:
            self.remove_parameter(param)
        param = self.get_parameter_by_name("tools")
        if param:
            self.remove_parameter(param)
        param = self.get_parameter_by_name("prompt_driver")
        if param:
            self.remove_parameter(param)
        group = self.get_parameter_by_name("Agent Abilities")
        if group:
            self.remove_parameter(group)

    def process(self) -> None:
        # Get input values
        params = self.parameter_values
        agent_dict = params.get("agent", None)

        if not agent_dict:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.getkey(value=f"{SERVICE}.{API_KEY_ENV_VAR}"),
                stream=True,
            )
            agent = Agent(prompt_driver=prompt_driver)
        else:
            agent = Agent().from_dict(agent_dict)

        prompt = params.get("prompt", None)
        if prompt:
            full_output = ""
            # Check and see if the prompt driver is a stream driver
            if self.is_stream(agent):
                # Run the agent
                for artifact in Stream(agent).run(prompt):
                    full_output += artifact.value
            else:
                # Run the agent
                result = agent.run(prompt)
                full_output = result.output.value
            self.parameter_output_values["output"] = full_output
        else:
            self.parameter_output_values["output"] = "Agent Created"

        self.parameter_output_values["agent"] = agent.to_dict()
