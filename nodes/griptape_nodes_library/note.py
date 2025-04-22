from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode


class Note(BaseNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: str = "",
    ) -> None:
        super().__init__(name, metadata)

        self.add_parameter(
            Parameter(
                name="note",
                default_value=value,
                type="str",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter your note here...",
                    "is_full_width": True,
                    "className": "text-xl",
                },
                tooltip="A helpful note",
            )
        )

    def process(self) -> None:
        pass
