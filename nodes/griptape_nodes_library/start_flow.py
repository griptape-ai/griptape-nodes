from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameter_Output
from griptape_nodes.exe_types.node_types import StartNode


class SimpleAgentNode(StartNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameter_Output())

    def process(self) -> None:
        pass
