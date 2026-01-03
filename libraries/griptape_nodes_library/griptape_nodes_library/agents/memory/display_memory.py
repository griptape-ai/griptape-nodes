import json
from typing import Any

from griptape.structures.agent import Agent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.exe_types.param_types.parameter_json import ParameterJson


class DisplayAgentMemory(ControlNode):
    """DisplayAgentMemory Node that displays the memory of an agent."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.agent = Parameter(
            name="agent",
            tooltip="Agent to extract memory from",
            input_types=["Agent"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )

        self.add_parameter(self.agent)
        self.memory_json = ParameterJson(
            name="memory",
            tooltip="The agent's memory as a JSON object",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.memory_json)

    def _get_memory_dict(self) -> dict[str, Any] | None:
        """Get and parse memory from agent, returning None if unavailable."""
        agent_dict = self.get_parameter_value("agent")
        if agent_dict is None:
            return None

        agent = Agent.from_dict(agent_dict)
        if agent is None or agent.conversation_memory is None:
            return None

        memory = agent.conversation_memory.to_json()

        # Handle case where to_json() returns a string
        if isinstance(memory, str):
            try:
                memory = json.loads(memory)
            except json.JSONDecodeError:
                return None

        # Ensure memory is a dict
        if not isinstance(memory, dict):
            return None

        return memory

    def _extract_value_from_artifact(self, artifact: Any) -> str:
        """Extract value from an artifact (dict with 'value' key or string)."""
        if isinstance(artifact, dict):
            return artifact.get("value", "")
        if isinstance(artifact, str):
            return artifact
        return ""

    def _transform_runs(self, memory: dict[str, Any]) -> list[dict[str, str]]:
        """Transform memory runs to extract just input/output values."""
        transformed_runs = []
        if "runs" not in memory:
            return transformed_runs

        runs = memory["runs"]
        if not isinstance(runs, list):
            return transformed_runs

        for run in runs:
            if not isinstance(run, dict):
                continue

            input_value = self._extract_value_from_artifact(run.get("input", ""))
            output_value = self._extract_value_from_artifact(run.get("output", ""))

            transformed_runs.append({"input": input_value, "output": output_value})

        return transformed_runs

    def _set_output(self, transformed_memory: dict[str, Any]) -> None:
        """Set the output parameter value."""
        self.parameter_output_values["memory"] = transformed_memory
        self.publish_update_to_parameter("memory", transformed_memory)

    def process(self) -> None:
        memory = self._get_memory_dict()
        if memory is None:
            self._set_output({"runs": []})
            return

        transformed_runs = self._transform_runs(memory)
        transformed_memory = {"runs": transformed_runs}
        self._set_output(transformed_memory)
