from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.options import Options


class CompareNumbers(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ControlParameterInput(
                tooltip="Compare Two Numbers",
                name="exec_in",
            )
        )
        true_param = ControlParameterOutput(
            tooltip="Flow to take when condition is True.",
            name="True",
        )
        true_param.ui_options = {"display_name": "True"}
        self.add_parameter(true_param)
        false_param = ControlParameterOutput(
            tooltip="Flow to take when condition is False.",
            name="False",
        )
        false_param._ui_options = {"display_name": "False"}
        self.add_parameter(false_param)
        self.add_parameter(
            Parameter(
                name="evaluate",
                tooltip="Evaluate the condition.",
                input_types=["str"],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["A == B", "A != B", "A < B", "A > B", "A <= B", "A >= B"])},
                default_value="==",
            )
        )
        self.add_parameter(
            Parameter(
                name="A",
                tooltip="First Number",
                input_types=["int", "float"],
                default_value=0,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="B",
                tooltip="Second Number",
                input_types=["int", "float"],
                default_value=0,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="result",
                tooltip="result of the condition.",
                input_types=["bool"],
                allowed_modes={ParameterMode.OUTPUT},
                default_value=False,
                ui_options={"hide": True},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name in ["evaluate", "A", "B"]:
            self.parameter_values["result"] = self.get_comparison()

        return super().after_value_set(parameter, value)

    def get_comparison(self) -> bool:
        value = self.get_parameter_value("evaluate")
        input_1 = self.get_parameter_value("A")
        input_2 = self.get_parameter_value("B")

        comparison_map = {
            "A == B": input_1 == input_2,
            "A != B": input_1 != input_2,
            "A < B": input_1 < input_2,
            "A > B": input_1 > input_2,
            "A <= B": input_1 <= input_2,
            "A >= B": input_1 >= input_2,
        }

        return comparison_map.get(value, False)

    def process(self) -> None:
        self.parameter_output_values["result"] = self.get_comparison()

    # Override this method.
    def get_next_control_output(self) -> Parameter | None:
        if "result" not in self.parameter_output_values:
            self.stop_flow = True
            return None
        if self.parameter_output_values["result"]:
            return self.get_parameter_by_name("True")
        return self.get_parameter_by_name("False")
