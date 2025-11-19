from typing import Any

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class Note(BaseNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            ParameterString(
                name="note",
                default_value=value,
                allow_input=False,
                allow_property=True,
                allow_output=False,
                multiline=True,
                placeholder_text="Enter your note here...",
                markdown=True,
                is_full_width=True,
                tooltip="A helpful note",
            )
        )

    def process(self) -> None:
        pass
