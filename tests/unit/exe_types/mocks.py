"""Mock classes for testing exe_types."""

from griptape_nodes.exe_types.node_types import BaseNode


class MockNode(BaseNode):
    """A mock node class for testing BaseNode functionality."""

    def run(self) -> None:
        pass

    def initialize(self) -> None:
        pass

    def process(self) -> None:
        pass
