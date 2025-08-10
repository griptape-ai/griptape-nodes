from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.video_utils import dict_to_video_url_artifact
from griptape_nodes_library.video.video_url_artifact import VideoUrlArtifact


class LoadVideo(DataNode):
    # Supported video file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_video_url_artifact,
            extract_url_func=lambda value: default_extract_url_from_artifact_value(
                artifact_value=value, artifact_classes=VideoUrlArtifact
            ),
            supported_extensions=self.SUPPORTED_EXTENSIONS,
            default_extension="mp4",
            url_content_type_prefix="video/",
        )

        self.video_parameter = Parameter(
            name="video",
            input_types=["VideoArtifact", "VideoUrlArtifact", "str"],
            type="VideoArtifact",
            output_type="VideoUrlArtifact",
            default_value=None,
            ui_options={
                "clickable_file_browser": True,
                "expander": True,
                "display_name": "Video or Path to Video",
            },
            tooltip="The loaded video.",
        )
        self.add_parameter(self.video_parameter)

        # Use the tethering utility to create the properly configured path parameter
        self.path_parameter = ArtifactPathTethering.create_path_parameter(
            name="path",
            config=self._tethering_config,
            display_name="File Path or URL",
            tooltip="Path to a local video file or URL to a video",
        )
        self.add_parameter(self.path_parameter)

        # Tethering helper: keeps video and path parameters in sync bidirectionally
        # When user uploads a file -> path shows the URL, when user enters path -> video loads that file
        self._tethering = ArtifactPathTethering(
            node=self,
            artifact_parameter=self.video_parameter,
            path_parameter=self.path_parameter,
            config=self._tethering_config,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Delegate tethering logic to helper
        self._tethering.on_after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get parameter values and assign to outputs
        video_artifact = self.get_parameter_value("video")
        self.parameter_output_values["video"] = video_artifact

        path_value = self.get_parameter_value("path")
        self.parameter_output_values["path"] = path_value
