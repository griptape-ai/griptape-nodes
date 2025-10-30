from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput, ControlParameterOutput, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options


class CompareStrings(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ControlParameterInput(
                tooltip="Compare Two Strings",
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
            ParameterString(
                name="evaluate",
                tooltip="Evaluate the condition.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(choices=["A == B", "A != B", "A < B", "A > B", "A <= B", "A >= B", "A in B", "A not in B"])
                },
                default_value="A == B",
            )
        )
        self.add_parameter(
            ParameterBool(
                name="case_sensitive",
                tooltip="Case Sensitive",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=True,
            )
        )
        self.add_parameter(
            ParameterString(
                name="A",
                tooltip="First String",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterString(
                name="B",
                tooltip="Second String",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            ParameterBool(
                name="result",
                tooltip="result of the condition.",
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
        case_sensitive = self.get_parameter_value("case_sensitive")
        input_1 = self.get_parameter_value("A")
        input_2 = self.get_parameter_value("B")

        if not case_sensitive:
            input_1 = input_1.lower()
            input_2 = input_2.lower()

        comparison_map = {
            "A == B": input_1 == input_2,
            "A != B": input_1 != input_2,
            "A < B": input_1 < input_2,
            "A > B": input_1 > input_2,
            "A <= B": input_1 <= input_2,
            "A >= B": input_1 >= input_2,
            "A in B": input_1 in input_2,
            "A not in B": input_1 not in input_2,
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
