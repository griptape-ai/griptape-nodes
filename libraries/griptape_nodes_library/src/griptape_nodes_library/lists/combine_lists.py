from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode


class CombineLists(ControlNode):
    """CombineLists Node that takes two lists and combines them into a single flattened list.

    The resulting list will contain all items from both input lists in order.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameters
        self.list_a = Parameter(
            name="list_a",
            tooltip="First list to combine",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.list_a)

        self.list_b = Parameter(
            name="list_b",
            tooltip="Second list to combine",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.list_b)

        self.output = Parameter(
            name="output",
            tooltip="Combined list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

    def process(self) -> None:
        # Get the lists from the input parameters
        list_a = self.get_parameter_value("list_a")
        list_b = self.get_parameter_value("list_b")

        # Validate inputs
        if not isinstance(list_a, list):
            list_a = []
        if not isinstance(list_b, list):
            list_b = []

        # Combine the lists
        combined_list = list_a + list_b

        self.parameter_output_values["output"] = combined_list
