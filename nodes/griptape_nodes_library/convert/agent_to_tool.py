from typing import Any

from griptape.drivers.structure_run.local import LocalStructureRunDriver
from griptape.structures import Agent as gtAgent
from griptape.tools import StructureRunTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.utilities import to_pascal_case

placeholder_description = "Tool created from an Agent"


class AgentToTool(DataNode):
    """Convert an Agent to a Tool that can be used by other Agents."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent"],
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
            )
        )

        # Name parameter for the Tool
        self.add_parameter(
            Parameter(
                name="name",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                default_value="Agent Tool",
                tooltip="Name for the Tool",
            )
        )

        def validate_tool_description(_param: Parameter, value: str) -> None:
            if not value:
                msg = f"{self.name} : A meaningful description is critical for an Agent to know when to use this tool."
                raise ValueError(msg)

        # Description parameter for the Tool
        self.add_parameter(
            Parameter(
                name="description",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Description for what the Tool does",
                },
                tooltip="Description for what the Tool does",
                validators=[validate_tool_description],
            )
        )

        self.add_parameter(
            Parameter(
                name="off_prompt",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="tool",
                input_types=["Tool"],
                type="Tool",
                output_type="Tool",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="",
            )
        )

    def process(self) -> None:
        """Convert the Agent to a Tool."""
        # Get the input values
        params = self.parameter_values
        agent = params.get("agent")
        name = params.get("name", "Agent Tool")
        description = params.get("description", placeholder_description)
        off_prompt = params.get("off_prompt", True)

        if type(agent) is dict:
            agent = gtAgent.from_dict(agent)

        if agent is None:
            self.parameter_output_values["tool"] = None
            return

        # The lambda ensures a fresh instance of the agent for each run
        driver = LocalStructureRunDriver(create_structure=lambda: agent)

        # The verbose description makes it work first-try instead of hitting formatting issues and retrying
        tool = StructureRunTool(
            name=to_pascal_case(name),
            description=f"{description}\n\nThis tool requires an 'args' parameter as a list of strings. "
            f'Example usage: {{ "values": {{ "args": ["your input here"] }} }}',
            structure_run_driver=driver,
            off_prompt=off_prompt,
        )

        self.parameter_output_values["tool"] = tool
