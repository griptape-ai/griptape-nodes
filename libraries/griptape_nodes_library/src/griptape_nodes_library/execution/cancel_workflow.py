from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class CancelWorkflow(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            ControlParameterInput(
                tooltip="Cancel Workflow Execution",
            )
        )
        self.add_parameter(
            Parameter(
                name="cancellation_reason",
                tooltip="Reason for cancelling the workflow",
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="Cancelled running workflow via Cancel Workflow Node.",
            )
        )

    def process(self) -> None:
        cancellation_reason = self.get_parameter_value("cancellation_reason")
        if not cancellation_reason:
            cancellation_reason = "Cancelled running workflow via Cancel Workflow Node."

        raise RuntimeError(cancellation_reason)
