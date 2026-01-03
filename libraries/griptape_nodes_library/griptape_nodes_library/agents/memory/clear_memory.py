from typing import Any

from griptape.structures.agent import Agent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class ClearMemory(ControlNode):
    """ClearMemory Node that clears an agent's conversation memory."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.agent = Parameter(
            name="agent",
            tooltip="Agent to clear memory for",
            input_types=["Agent"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )

        self.add_parameter(self.agent)

    def _get_agent(self) -> Agent | None:
        """Get the agent object from the parameter value, returning None if unavailable."""
        agent_dict = self.get_parameter_value("agent")
        if agent_dict is None:
            return None

        agent = Agent.from_dict(agent_dict)
        if agent is None or agent.conversation_memory is None:
            return None

        return agent

    def process(self) -> None:
        agent = self._get_agent()
        if agent is None or agent.conversation_memory is None:
            return

        # Clear all conversation memory runs
        agent.conversation_memory.runs = []

        # Output the updated agent
        updated_agent_dict = agent.to_dict()
        self.parameter_output_values["agent"] = updated_agent_dict
        self.publish_update_to_parameter("agent", updated_agent_dict)
