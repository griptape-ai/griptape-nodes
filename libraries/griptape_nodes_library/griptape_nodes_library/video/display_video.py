from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode


class DisplayVideo(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add parameter for the image
        self.add_parameter(
            Parameter(
                name="video",
                default_value=value,
                input_types=["VideoUrlArtifact"],
                output_type="VideoArtifact",
                type="VideoArtifact",
                tooltip="The video to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        # Simply output the input image
        self.parameter_output_values["image"] = self.parameter_values.get("image")
