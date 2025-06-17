from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import StartNode


class StartFlow(StartNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_node_element(
            ParameterMessage(
                name="input_message",
                variant="info",
                title="Workflow Inputs",
                value="Add input parameters to drive your workflow.",
            )
        )

        self.first_param = Parameter(
            name="input_prompt",
            tooltip="An input to drive your workflow.",
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            type="str",
            default_value="",
            ui_options={"is_custom": True, "is_user_defined": True, "is_full_width": False},
        )

        self.add_node_element(self.first_param)

    def process(self) -> None:
        pass
