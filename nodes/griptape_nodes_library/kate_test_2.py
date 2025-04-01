from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger

class TestNode2(ControlNode):
    """Save text to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add text input parameter
        self.add_parameter(
            Parameter(
                name="text",
                allowed_modes={ParameterMode.INPUT},
                input_types=["AwesomeClass"],
                output_type="str",
                default_value="",
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="display",
                allowed_modes={ParameterMode.PROPERTY,ParameterMode.OUTPUT},
                input_types=["str"],
                output_type="str",
                default_value="",
                tooltip="",
            )
        )


    def process(self) -> None:
       val = self.parameter_values["text"]
       val.process()
       print(val.name)
       self.parameter_output_values["display"] = val.name
