from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.video_utils import SUPPORTED_VIDEO_EXTENSIONS, dict_to_video_url_artifact


class LoadVideo(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_video_url_artifact,
            extract_url_func=lambda value: default_extract_url_from_artifact_value(
                artifact_value=value, artifact_classes=VideoUrlArtifact
            ),
            supported_extensions=SUPPORTED_VIDEO_EXTENSIONS,
            default_extension="mp4",
            url_content_type_prefix="video/",
        )

        self.video_parameter = Parameter(
            name="video",
            input_types=["VideoUrlArtifact", "VideoArtifact", "str"],
            type="VideoUrlArtifact",
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

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Delegate to tethering helper - only artifact parameter can receive connections
        self._tethering.on_incoming_connection(target_parameter)
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # Delegate to tethering helper - only artifact parameter can have connections removed
        self._tethering.on_incoming_connection_removed(target_parameter)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def before_value_set(self, parameter: Parameter, value: Any) -> Any:
        # Delegate to tethering helper for dynamic settable control
        return self._tethering.on_before_value_set(parameter, value)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Delegate tethering logic to helper for value synchronization and settable restoration
        self._tethering.on_after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get parameter values and assign to outputs
        video_artifact = self.get_parameter_value("video")
        self.parameter_output_values["video"] = video_artifact

        path_value = self.get_parameter_value("path")
        self.parameter_output_values["path"] = path_value
