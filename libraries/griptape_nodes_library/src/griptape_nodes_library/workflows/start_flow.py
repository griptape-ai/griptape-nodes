from typing import Any

from griptape_nodes.exe_types.node_types import StartNode


class StartFlow(StartNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        if metadata is None:
            metadata = {}
        metadata["showaddparameter"] = True
        super().__init__(name, metadata)

    def process(self) -> None:
        pass
