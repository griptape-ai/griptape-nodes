from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter
from griptape_nodes.exe_types.node_types import BaseNode


class IfElse(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ControlParameterOutput(
                tooltip="If-else connection",
                name="True",
            )
        )
        self.add_parameter(
            ControlParameterOutput(
                tooltip="If-else connection",
                name="False",
            )
        )
        self.add_parameter(
            ControlParameterInput(
                tooltip="If-else connection",
                name="exec_in",
            )
        )
        self.add_parameter(Parameter(name="evaluate", tooltip="Evalutes where to go", type="bool", default_value=True))

    def process(self) -> None:
        return

    # Override this method.
    def get_next_control_output(self) -> Parameter | None:
        if self.get_parameter_value("evaluate"):
            return self.get_parameter_by_name("True")
        return self.get_parameter_by_name("False")
