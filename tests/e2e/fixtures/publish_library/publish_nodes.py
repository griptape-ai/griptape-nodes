"""Fixture nodes for tests/e2e/test_packaged_flow_publish.py: a start, an end, and a node to package."""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode, EndNode, StartNode


class PublishStartNode(StartNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class PublishEndNode(EndNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class PublishEchoNode(DataNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(
            Parameter(
                name="text",
                type="str",
                default_value="",
                tooltip="Text to echo",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="result",
                type="str",
                default_value="",
                tooltip="Echoed text",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["result"] = self.get_parameter_value("text") or ""
