from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class CreateInteger(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        # Add output parameter for the string
        self.add_parameter(
            Parameter(
                name="integer",
                default_value=value,
                output_type="int",
                type="int",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="An integer",
            )
        )

    def process(self) -> None:
        # Simply output the default value or any updated property value
        self.parameter_output_values["integer"] = self.parameter_values["integer"]
