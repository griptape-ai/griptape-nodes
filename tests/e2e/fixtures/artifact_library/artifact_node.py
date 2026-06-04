"""ArtifactNode used by tests/e2e/test_headless_deferred_imports.py.

Produces a FakeArtifact output value. When the workflow is saved, this value is
pickled into top_level_unique_values_dict and FakeArtifact's module (this file,
loaded dynamically by the engine) is registered as a dynamic library module.
That triggers the deferred-import path: the generator must emit
`from artifact_node import FakeArtifact` inside build_workflow() rather than at
module top, so it runs after RegisterLibraryFromFileRequest sets up sys.path.
"""

from __future__ import annotations

from griptape.artifacts.base_artifact import BaseArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class FakeArtifact(BaseArtifact):
    """Minimal artifact that carries a string value."""

    value: str = ""

    def to_text(self) -> str:
        return self.value


class ArtifactNode(DataNode):
    def __init__(self, name: str, metadata: dict | None = None) -> None:
        super().__init__(name, metadata=metadata)
        self.add_parameter(
            Parameter(
                name="artifact",
                tooltip="A FakeArtifact output",
                type="FakeArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        self.parameter_output_values["artifact"] = FakeArtifact(value="hello")
