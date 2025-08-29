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

        # Add parameter for the video
        self.add_parameter(
            Parameter(
                name="video",
                default_value=value,
                input_types=["VideoUrlArtifact", "VideoArtifact"],
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="The video to display",
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        # Simply output the input video
        self.parameter_output_values["video"] = self.parameter_values.get("video")
