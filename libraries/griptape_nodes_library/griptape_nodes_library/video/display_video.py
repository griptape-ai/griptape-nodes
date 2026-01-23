from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo


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
            ParameterVideo(
                name="video",
                default_value=value,
                tooltip="The video to display",
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
