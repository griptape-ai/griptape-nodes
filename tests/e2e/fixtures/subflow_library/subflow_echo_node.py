"""Fixture nodes for subflow e2e tests.

EchoNode: copies its ``text`` input to its ``text`` output.

SubflowGroupNode: minimal concrete SubflowNodeGroup that runs all child nodes
in-process (LOCAL execution).  Used to verify that parameter values survive
the subflow round-trip without corruption.
"""

from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup
from griptape_nodes.exe_types.node_types import DataNode


class EchoNode(DataNode):
    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata=metadata)
        self.add_parameter(
            Parameter(
                name="text",
                tooltip="Text to echo",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["text"] = self.get_parameter_value("text") or ""


class SubflowGroupNode(SubflowNodeGroup):
    """Minimal concrete SubflowNodeGroup for fixture use."""

    async def aprocess(self) -> None:
        await self.execute_subflow()

    def process(self) -> Any:
        pass
