import logging
import threading

from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import EventBus
from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.retained_mode.events.base_events import ProgressEvent
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

    def process(self) -> AsyncResult[str]:
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
            agent = Agent.from_dict(agent_dict)

        prompt = params.get("prompt", None)
        agent = self.set_context(agent)

        if prompt:
            full_output = ""
            # Check and see if the prompt driver is a stream driver
            if self.is_stream(agent):
                # Run the agent
                full_output = yield (lambda shutdown_event: self._process(agent, prompt, shutdown_event))
            else:
                # Run the agent
                full_output = (
                    yield lambda shutdown_event: agent.run(prompt).output.value if not shutdown_event.is_set() else ""
                )
            self.parameter_output_values["output"] = full_output
        else:
            self.parameter_output_values["output"] = "Agent Created"

        self.parameter_output_values["agent"] = agent.to_dict()

    def _process(self, agent: Agent, prompt: str, shutdown_event: threading.Event) -> str:
        # Check if the event is already set before starting
        if shutdown_event.is_set():
            output = ""
            return ""
        stream = Stream(agent)
        output = ""
        for artifact in stream.run(prompt):
            # Check if shutdown is requested during processing
            if shutdown_event.is_set():
                output = ""
                return ""  # Return nothing
            # SEND AN EVENT HERE
            EventBus.publish_event(ProgressEvent(value=artifact.value, node_name=self.name, parameter_name="output"))
            output += artifact.value
        return output
