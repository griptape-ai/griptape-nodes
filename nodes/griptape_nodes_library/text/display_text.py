from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayText(DataNode):
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
                name="text",
                default_value=value,
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="The text content to display",
                ui_options={"multiline": True},
            )
        )

    def process(self) -> None:
        # Simply output the default value or any updated property value
        self.parameter_output_values["text"] = self.parameter_values["text"]
