from typing import Any

from griptape_nodes.exe_types.core_types import ControlParameter_Input
from griptape_nodes.exe_types.node_types import NodeBase


class gnEndFlow(NodeBase):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameter_Input())

    def process(self) -> None:
        pass
