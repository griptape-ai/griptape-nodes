from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter
from griptape_nodes.exe_types.node_types import BaseNode


class IfElse(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ControlParameterInput(
                tooltip="If-Else Control Input",
                name="exec_in",
            )
        )
        then_param = ControlParameterOutput(
            tooltip="If-else connection to go down if condition is met.",
            name="Then",
        )
        then_param.ui_options = {"display_name": "Then"}
        self.add_parameter(then_param)
        else_param = ControlParameterOutput(
            tooltip="If-else connection to go down if condition is not met.",
            name="Else",
        )
        else_param._ui_options = {"display_name": "Else"}
        self.add_parameter(else_param)
        self.add_parameter(
            Parameter(
                name="evaluate",
                tooltip="Evaluates where to go",
                input_types=["bool", "int", "str"],
                output_type="bool",
                type="bool",
                default_value=False,
            )
        )

    def process(self) -> None:
        value = self.get_parameter_value("evaluate")
        self.parameter_output_values["evaluate"] = value

    # Override this method.
    def get_next_control_output(self) -> Parameter | None:
        if "evaluate" not in self.parameter_output_values:
            self.stop_flow = True
            return None
        if self.parameter_output_values["evaluate"]:
            return self.get_parameter_by_name("Then")
        return self.get_parameter_by_name("Else")
