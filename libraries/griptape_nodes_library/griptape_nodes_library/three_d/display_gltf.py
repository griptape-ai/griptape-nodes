from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayGLTF(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add parameter for the GLTF file
        self.add_parameter(
            Parameter(
                name="gltf",
                default_value=value,
                input_types=["GLTFArtifact", "GLTFUrlArtifact"],
                output_type="GLTFArtifact",
                type="GLTFArtifact",
                tooltip="The GLTF file to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        # Simply output the input GLTF file
        self.parameter_output_values["gltf"] = self.parameter_values.get("gltf")
