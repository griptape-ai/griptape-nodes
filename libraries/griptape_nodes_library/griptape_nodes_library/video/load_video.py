from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactPathValidator,
    ArtifactTetheringConfig,
)
from griptape_nodes_library.utils.video_utils import _extract_url_from_video_value, dict_to_video_url_artifact


class LoadVideo(DataNode):
    # Supported video file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_video_url_artifact,
            extract_url_func=_extract_url_from_video_value,
            supported_extensions=self.SUPPORTED_EXTENSIONS,
            default_extension="mp4",
            url_content_type_prefix="video/",
        )

        self.video_parameter = Parameter(
            name="video",
            input_types=["VideoArtifact", "VideoUrlArtifact"],
            type="VideoArtifact",
            output_type="VideoUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The loaded video.",
        )
        self.add_parameter(self.video_parameter)

        self.path_parameter = Parameter(
            name="path",
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="Path to a local video file or URL to a video",
            ui_options={"display_name": "File Path or URL"},
        )

        self.path_parameter.add_trait(
            FileSystemPicker(
                allow_directories=False,
                allow_files=True,
                file_types=list(self.SUPPORTED_EXTENSIONS),
            )
        )

        self.path_parameter.add_trait(
            ArtifactPathValidator(
                supported_extensions=self.SUPPORTED_EXTENSIONS,
                url_content_type_prefix="video/",
            )
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
        # Get outputs from tethering helper
        video_artifact = self._tethering.get_artifact_output()
        if video_artifact is not None:
            self.parameter_output_values["video"] = video_artifact

        self.parameter_output_values["path"] = self._tethering.get_path_output()
