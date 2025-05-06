from typing import Any

from griptape_nodes.exe_types.core_types import (
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import EndNode


class EndFlow(EndNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ParameterList(
                name="image",
                input_types=["image"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="text",
                input_types=["str"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="float",
                input_types=["float"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="integer",
                input_types=["int"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="boolean",
                input_types=["bool"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )

    def process(self) -> None:
        pass
