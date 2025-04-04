from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes.retained_mode.griptape_nodes import logger
from nodes.griptape_nodes_library.agents.base_agent_node import BaseAgentNode

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class CreateAgentNode(BaseAgentNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def process(self) -> None:
        # Get input values
        params = self.parameter_values
        prompt_driver = params.get("prompt_driver", self.get_default_prompt_driver())

        kwargs = {}

        kwargs["prompt_driver"] = prompt_driver

        agent_dict = params.get("agent", None)

        # Get any tools
        # append any tools to the already existing tools if there are any.
        tools = params.get("tools", None)
        if tools:
            logger.info("Tools found, adding to agent")
            if isinstance(tools, list):
                tools = [tool.to_dict() for tool in tools]
            else:
                tools = [tools.to_dict()]
            kwargs["tools"] = tools
        else:
            logger.info("No tools found")
        # Get any rules
        rulesets = self.valid_or_fallback("rulesets", None)
        if rulesets:
            kwargs["rulesets"] = [rulesets]

        agent = None
        if not agent_dict:
            logger.info("No agent input, creating one")
            # Create the Agent
            agent = Agent(**kwargs)
        else:
            agent = Agent().from_dict(agent_dict)
        # Otherwise, append rules and tools to the existing agent

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
            self.parameter_output_values["agent_response"] = full_output
        else:
            self.parameter_output_values["agent_response"] = "Agent Created"

        self.parameter_output_values["agent"] = agent.to_dict()
