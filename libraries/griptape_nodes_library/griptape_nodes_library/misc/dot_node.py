from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode


class DotNode(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="value",
                default_value=None,
                output_type="all",
                type="any",
                tooltip="Pass-through value",
            )
        )

    def process(self) -> None:
        self.parameter_output_values["value"] = self.parameter_values.get("value")
