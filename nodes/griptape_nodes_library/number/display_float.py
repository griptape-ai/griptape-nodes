from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayFloat(DataNode):
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
                name="float",
                default_value=value,
                type="float",
                tooltip="The number to display",
            )
        )

    def process(self) -> None:
        # Simply output the default value or any updated property value
        self.parameter_output_values["float"] = self.parameter_values["float"]
