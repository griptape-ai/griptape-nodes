from typing import Any, cast

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class ForLoop(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="looped_input",
                input_types=["list[str]"],
                type="str",
                default_value=[],
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="list_output",
                tooltip = "",
                type="ImageArtifact",
                output_type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                settable=True
            )
        )
        self.add_parameter(
            Parameter(
                name="flow",
                tooltip="The flow to rerun",
                type="ControlFlow",
                allowed_modes={ParameterMode.INPUT}
            )
        )

    def process(self) -> None:
        loop = self.get_parameter_value("looped_input")
        # Get the list we are going to loop over. ForEach Loop
        flow = self.get_parameter_value("flow")
        for prompt in loop:
            flow = cast("ControlFlow", flow)
            start_node_queue = flow.get_start_node_queue()
            start_node = start_node_queue.get() if start_node_queue is not None else None
            if start_node is not None:
                start_node = cast("ControlNode", start_node)
                start_node.set_parameter_value("prompt",prompt)
                GriptapeNodes.handle_request(StartFlowRequest("SubFlow_1"))
            # Flow then executes. Hooray!
            end_node = flow.end_node
            if end_node is not None:
                self.parameter_output_values["list_output"] = end_node.parameter_output_values["output"]

