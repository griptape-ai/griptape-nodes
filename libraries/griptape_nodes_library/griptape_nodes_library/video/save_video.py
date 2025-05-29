from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button
from griptape_nodes_library.utils.video_utils import dict_to_video_url_artifact
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact

DEFAULT_FILENAME = "griptape_nodes.mp4"


def to_video_artifact(video: Any | dict) -> Any:
    """Convert a video or a dictionary to a VideoArtifact."""
    if isinstance(video, dict):
        return dict_to_video_url_artifact(video)
    return video


class SaveVideo(ControlNode):
    """Save a video to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add video input parameter
        self.add_parameter(
            Parameter(
                name="video",
                input_types=["VideoArtifact", "VideoUrlArtifact", "dict"],
                type="VideoUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The video to save to file",
            )
        )

        # Add output path parameter
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The output filename with extension (.mp4, .avi, etc.)",
                traits={Button(button_type="save")},
            )
        )

    def process(self) -> None:
        video = self.parameter_values.get("video")

        if not video:
            logger.info("No video provided to save")
            return

        output_file = self.parameter_values.get("output_path", DEFAULT_FILENAME)

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        try:
            video_artifact = to_video_artifact(video)

            if isinstance(video_artifact, VideoUrlArtifact):
                # For VideoUrlArtifact, we need to get the bytes from the URL
                # This might need adjustment based on how VideoUrlArtifact is implemented
                video_bytes = video_artifact.to_bytes()
            else:
                # Assume it has a value attribute with bytes
                video_bytes = video_artifact.value

            saved_path = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, output_file)

            success_msg = f"Saved video: {saved_path}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving video: {error_message}"
            raise ValueError(msg) from e
