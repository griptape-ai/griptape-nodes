from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class WaitText(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        if not self.get_parameter_value("text"):
            self.stop_flow = True
            return

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "text":
            flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
            GriptapeNodes().handle_request(StartFlowRequest(flow_name=flow_name))
        return super().after_value_set(parameter, value, modified_parameters_set)
