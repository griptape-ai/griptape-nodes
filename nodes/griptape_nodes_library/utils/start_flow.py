from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameterOutput
from griptape_nodes.exe_types.node_types import StartNode


class StartFlow(StartNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameterOutput())

    def process(self) -> None:
        pass
