from typing import Any

from griptape.artifacts import ErrorArtifact, TextArtifact
from griptape.memory.structure import Run
from griptape.structures.agent import Agent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class SummarizeAgentMemory(ControlNode):
    """SummarizeMemory Node that summarizes an agent's conversation memory and replaces it with a single summary run."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.agent = Parameter(
            name="agent",
            tooltip="Agent to summarize memory for",
            input_types=["Agent"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )

        self.add_parameter(self.agent)

        self.summary = ParameterString(
            name="summary",
            tooltip="The summary of the agent's conversation memory",
            multiline=True,
            allow_input=False,
            allow_property=False,
        )

        self.add_parameter(self.summary)

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

        # Check if there are any runs to summarize
        if len(agent.conversation_memory.runs) == 0:
            # No memory to summarize, just output the agent as-is
            updated_agent_dict = agent.to_dict()
            self.parameter_output_values["agent"] = updated_agent_dict
            self.publish_update_to_parameter("agent", updated_agent_dict)
            return

        # Run the agent with the summarize prompt
        prompt = "summarize our conversation. Include specific and useful details about the conversation, but only output only the summary, no other text. Do not include this exchange as part of that summary."
        agent.run(prompt)

        # Get the summary from the agent's output
        if agent.output is None:
            return

        # Check for errors
        if isinstance(agent.output, ErrorArtifact):
            return

        summary_text = agent.output.value if hasattr(agent.output, "value") else str(agent.output)

        # Success path - set summary and replace memory
        self.parameter_output_values["summary"] = summary_text
        self.publish_update_to_parameter("summary", summary_text)

        agent.conversation_memory.runs = [
            Run(
                input=TextArtifact(value="conversation summary"),
                output=TextArtifact(value=summary_text),
            )
        ]

        updated_agent_dict = agent.to_dict()
        self.parameter_output_values["agent"] = updated_agent_dict
        self.publish_update_to_parameter("agent", updated_agent_dict)
