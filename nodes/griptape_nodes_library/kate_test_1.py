from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger

class AwesomeClass:
    name:str = "Kate"

    def process(self):
        self.name = f"How Awesome Is {self.name}"


class TestNode1(ControlNode):
    """Save text to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add text input parameter
        self.add_parameter(
            Parameter(
                name="text",
                allowed_modes={ParameterMode.OUTPUT},
                input_types=["AwesomeClass"],
                output_type="AwesomeClass",
                default_value=AwesomeClass(),
                tooltip="",
            )
        )


    def process(self) -> None:
       val =self.parameter_values["text"]
       val.process()
       print(val.name)
       self.parameter_output_values["text"] = val
