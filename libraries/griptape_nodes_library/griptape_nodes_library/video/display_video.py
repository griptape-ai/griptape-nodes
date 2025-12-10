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

    def _update_output(self) -> None:
        """Update the output parameter."""
        video = self.get_parameter_value("video")
        self.parameter_output_values["video"] = video

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "video":
            self._update_output()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node during execution."""
        self._update_output()
