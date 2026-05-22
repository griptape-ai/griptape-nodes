"""Echo node used by tests/e2e/test_standalone_workflow_execution.py.

Minimal BaseNode subclass that copies its `text` input to its `result` output. Kept
intentionally tiny so the e2e fixture has zero pip dependencies and registers cleanly
in a subprocess that has only the engine itself on its Python path.
"""

from __future__ import annotations

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
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
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="result",
                tooltip="Echoed text",
                type="str",
                default_value="",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        text = self.get_parameter_value("text") or ""
        self.parameter_output_values["result"] = text
