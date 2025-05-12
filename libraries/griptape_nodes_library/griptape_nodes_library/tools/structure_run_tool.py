from typing import Any

from griptape.tools import StructureRunTool as GtStructureRunTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.tools.base_tool import BaseTool


class StructureRun(BaseTool):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

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
                name="structure_run_config",
                input_types=["Structure Run Driver"],
                type="Structure Run Driver",
                output_type="Structure Run Driver",
                default_value=False,
                tooltip="Connect structure_run_config. If not supplied, we will use the Griptape Cloud Prompt Model.",
            )
        )

    def process(self) -> None:
        description = self.parameter_values.get("description", "Run a Structure")
        off_prompt = self.parameter_values.get("off_prompt", False)
        driver = self.parameter_values.get("structure_run_config", None)

        if driver is None:
            msg = "Driver is required to create the StructureRunTool"
            raise ValueError(msg)

        # Create the tool
        tool = GtStructureRunTool(description=description, off_prompt=off_prompt, structure_run_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool
