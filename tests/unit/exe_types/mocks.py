"""Mock classes for testing exe_types."""

from typing import Any

from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode


class MockNode(BaseNode):
    """A mock node class for testing BaseNode functionality."""

    def __init__(self, name: str = "mock_node", process_result: Any = None, **kwargs):
        super().__init__(name=name, **kwargs)
        self._process_result = process_result

    def run(self) -> None:
        pass

    def initialize(self) -> None:
        pass

    def process(self) -> AsyncResult | None:
        return self._process_result
