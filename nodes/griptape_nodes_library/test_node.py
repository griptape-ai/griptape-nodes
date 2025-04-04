
from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from traits.minmax import MinMax


class TestTraitNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Utility"
        self.description = "f"
        self.add_parameter(
            Parameter(
                name="number1",
                input_types=["int"],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="",
                traits={MinMax},
            )
        )
        self.add_parameter(
            Parameter(
                name="number2",
                input_types=["int"],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={MinMax},
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="sum",
                input_types=["int"],
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="",
            )
        )

    def process(self) -> None:
        # Get api key
        val1 = self.parameter_values["number1"]
        val2 = self.parameter_values["number2"]
        self.parameter_output_values["sum"] = val1 + val2
