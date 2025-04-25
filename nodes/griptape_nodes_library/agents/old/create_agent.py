from griptape.structures import Agent as gtAgent
from griptape.utils import Stream

from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.agents.base_agent import BaseAgent

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class Agent(BaseAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def get_tools(self) -> list:
        tools = self.get_parameter_value("tools")
        if tools:
            if not isinstance(tools, list):
                tools = [tools]
            return tools
        return []

    def get_rulesets(self) -> list:
        rulesets = self.get_parameter_value("rulesets")
        if rulesets:
            if not isinstance(rulesets, list):
                rulesets = [rulesets]
            return rulesets
        return []

    def process(
        self,
    ) -> AsyncResult[None]:
        # Get input values
        params = self.parameter_values
        prompt_driver = params.get("prompt_driver", self.get_default_prompt_driver())

        kwargs = {}

        kwargs["prompt_driver"] = prompt_driver

        agent_dict = params.get("agent", None)

        # Get any tools
        # append any tools to the already existing tools if there are any.
        kwargs["tools"] = self.get_tools()

        # Get any rules
        kwargs["rulesets"] = self.get_rulesets()

        agent = None
        if not agent_dict:
            logger.debug("No agent input, creating one")
            # Create the Agent
            agent = gtAgent(**kwargs)
        else:
            agent = gtAgent.from_dict(agent_dict)
        # Otherwise, append rules and tools to the existing agent

        prompt = params.get("prompt", None)
        agent = self.set_context(agent)
        if prompt:
            # Check and see if the prompt driver is a stream driver
            if self.is_stream(agent):
                yield (lambda: self._process(agent, prompt))
            else:
                # Run the agent
                full_output = yield lambda: agent.run(prompt).output.value
                self.parameter_output_values["output"] = full_output
        else:
            self.parameter_output_values["output"] = "Agent Created"

        self.parameter_output_values["agent"] = agent.to_dict()

    def _process(self, agent: gtAgent, prompt: str) -> None:
        stream = Stream(agent)
        for artifact in stream.run(prompt):
            self.append_value_to_parameter(parameter_name="output", value=artifact.value)
