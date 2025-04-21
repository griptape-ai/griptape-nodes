from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterInput
from griptape_nodes.exe_types.node_types import BaseNode


class EndFlow(BaseNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameterInput())

    def process(self) -> None:
        pass
