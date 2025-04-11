import logging
from collections.abc import Iterator
from typing import cast

from griptape.artifacts import TextArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent, Structure
from griptape.utils import Stream

from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes_library.agents.create_agent import CreateAgent

logger = logging.getLogger("griptape_nodes")


DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class RunAgent(CreateAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Remove unused inputs

        # Remove all Agent Configurations
        self.remove_node_element(self.agent_configuration_group)

        # Remove unused parameters
        param = self.get_parameter_by_name("rulesets")
        if param:
            self.remove_parameter(param)
        param = self.get_parameter_by_name("tools")
        if param:
            self.remove_parameter(param)
        param = self.get_parameter_by_name("prompt_driver")
        if param:
            self.remove_parameter(param)

    def process(self) -> AsyncResult[Iterator[TextArtifact] | Structure]:
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
        agent = self.set_context(agent)

        if prompt:
            full_output = ""
            # Check and see if the prompt driver is a stream driver
            if self.is_stream(agent):
                # Run the agent
                agent_stream = cast("Iterator", (yield lambda: Stream(agent).run(prompt)))
                for artifact in agent_stream:
                    full_output += artifact.value
            else:
                # Run the agent
                result = cast("Structure", (yield lambda: agent.run(prompt)))
                full_output = result.output.value
            self.parameter_output_values["output"] = full_output
        else:
            self.parameter_output_values["output"] = "Agent Created"

        self.parameter_output_values["agent"] = agent.to_dict()
