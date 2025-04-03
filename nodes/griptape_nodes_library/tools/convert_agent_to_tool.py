from griptape.drivers.structure_run.local import LocalStructureRunDriver
from griptape.tools import StructureRunTool

from griptape_nodes_library.tools.base_tool import BaseToolNode
from griptape_nodes_library.utilities import to_pascal_case


class ConvertAgentToToolNode(BaseToolNode):
    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", False)
        agent = self.parameter_values.get("agent", None)
        name = self.parameter_values.get("name", "Give the agent a name")
        description = self.parameter_values.get("description", "Describe what the agent should be used for")

        if agent:
            # Create a local structure function
            driver = LocalStructureRunDriver(create_structure=lambda: agent)

            # Create the tool
            tool = StructureRunTool(
                name=to_pascal_case(name),
                description=description,
                structure_run_driver=driver,
                off_prompt=off_prompt,
            )

            # Set the output
            self.parameter_output_values["tool"] = tool
        else:
            # Handle the case where no agent is provided
            self.parameter_output_values["tool"] = None
