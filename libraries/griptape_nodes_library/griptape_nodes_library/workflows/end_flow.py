from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import EndNode


class EndFlow(EndNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_node_element(
            ParameterMessage(
                name="output_message",
                variant="info",
                title="Output Message",
                value="Collect the output from your workflow in various parameters here.",
                ui_options={"is_full_width": True},
            )
        )
        self.workflow_output = Parameter(
            name="workflow_output",
            tooltip="The output from your workflow",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            type="string",
            default_value="",
            ui_options={
                "is_custom": True,
                "is_user_added": True,
                "placeholder_text": "The output from your workflow",
            },
        )

        self.add_parameter(self.workflow_output)

    def process(self) -> None:
        pass
