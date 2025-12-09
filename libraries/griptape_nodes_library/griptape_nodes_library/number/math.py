from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options

operations = [
    ("add", "A + B"),
    ("subtract", "A - B"),
    ("multiply", "A * B"),
    ("divide", "A / B"),
    ("modulo", "A % B"),
    ("power", "A ^ B"),
    ("sqrt", "√A"),
    ("average", "avg(A, B)"),
    ("min", "min(A, B)"),
    ("max", "max(A, B)"),
    ("round", "round(A)"),
    ("ceil", "⌈A⌉"),
    ("floor", "⌊A⌋"),
    ("abs", "|A|"),
    ("sin", "sin(A)"),
]
CHOICES = [f"{op} [{expr}]" for op, expr in operations]


class Math(ControlNode):
    """Math node for performing mathematical operations.

    Extends ControlNode to support control flow, enabling use in For loops
    and other control flow constructs.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="operation",
                tooltip="Operation to perform.",
                type="str",
                default_value=CHOICES[0],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=CHOICES)},
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
                type="float",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=0.0,
                ui_options={"hide": False},
            )
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name in ["operation", "A", "B"]:
            result = self.calculate_operation()
            self.parameter_output_values["result"] = result
            self.publish_update_to_parameter("result", result)

            # Update B parameter visibility based on operation
            if parameter.name == "operation":
                choice = self.get_parameter_value("operation")
                operation = choice.split(" [")[0]
                if operation in ["sqrt", "abs", "round", "ceil", "floor", "sin"]:
                    self.hide_parameter_by_name("B")
                else:
                    self.show_parameter_by_name("B")

        return super().after_value_set(parameter, value)

    def _handle_unary(self, operation: str, value: float) -> float:
        import math

        ops = {"sqrt": math.sqrt, "abs": abs, "round": round, "ceil": math.ceil, "floor": math.floor, "sin": math.sin}
        return ops.get(operation, lambda: 0.0)(value)

    def _handle_binary(self, operation: str, a: float, b: float) -> float:
        ops = {
            "add": lambda x, y: x + y,
            "subtract": lambda x, y: x - y,
            "multiply": lambda x, y: x * y,
            "divide": lambda x, y: x / y if y != 0 else float("inf"),
            "modulo": lambda x, y: x % y if y != 0 else float("inf"),
            "power": lambda x, y: x**y,
        }
        return ops.get(operation, lambda: 0.0)(a, b)

    def _handle_list_ops(self, operation: str, values: list[float]) -> float:
        import statistics

        ops = {"average": statistics.mean, "min": min, "max": max}
        return ops.get(operation, lambda: 0.0)(values)

    def calculate_operation(self) -> float:
        choice = self.get_parameter_value("operation")
        operation = choice.split(" [")[0]  # Extract just the operation name
        input_1 = self.get_parameter_value("A")
        input_2 = self.get_parameter_value("B")

        if operation in ["sqrt", "abs", "round", "ceil", "floor", "sin"]:
            return self._handle_unary(operation, input_1)
        if operation in ["add", "subtract", "multiply", "divide", "modulo", "power"]:
            return self._handle_binary(operation, input_1, input_2)
        if operation in ["average", "min", "max"]:
            return self._handle_list_ops(operation, [input_1, input_2])
        return 0.0

    def process(self) -> None:
        self.parameter_output_values["result"] = self.calculate_operation()
