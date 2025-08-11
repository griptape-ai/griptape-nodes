from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact
from griptape_nodes_library.utils.artifact_path_tethering import (
    ArtifactPathTethering,
    ArtifactPathValidator,
    ArtifactTetheringConfig,
    default_extract_url_from_artifact_value,
)
from griptape_nodes_library.utils.audio_utils import dict_to_audio_url_artifact


class LoadAudio(DataNode):
    # Supported audio file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Configuration for artifact tethering
        self._tethering_config = ArtifactTetheringConfig(
            dict_to_artifact_func=dict_to_audio_url_artifact,
            extract_url_func=lambda value: default_extract_url_from_artifact_value(
                artifact_value=value, artifact_classes=AudioUrlArtifact
            ),
            supported_extensions=self.SUPPORTED_EXTENSIONS,
            default_extension="mp3",
            url_content_type_prefix="audio/",
        )

        self.audio_parameter = Parameter(
            name="audio",
            input_types=["AudioArtifact", "AudioUrlArtifact"],
            type="AudioArtifact",
            output_type="AudioUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The loaded audio.",
        )
        self.add_parameter(self.audio_parameter)

        self.path_parameter = Parameter(
            name="path",
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="Path to a local audio file or URL to an audio",
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
                url_content_type_prefix="audio/",
            )
        )

        self.add_parameter(self.path_parameter)

        # Tethering helper: keeps audio and path parameters in sync bidirectionally
        # When user uploads a file -> path shows the URL, when user enters path -> audio loads that file
        self._tethering = ArtifactPathTethering(
            node=self,
            artifact_parameter=self.audio_parameter,
            path_parameter=self.path_parameter,
            config=self._tethering_config,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Delegate tethering logic to helper
        self._tethering.on_after_value_set(parameter, value)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get outputs from tethering helper
        audio_artifact = self._tethering.get_artifact_output()
        if audio_artifact is not None:
            self.parameter_output_values["audio"] = audio_artifact

        self.parameter_output_values["path"] = self._tethering.get_path_output()
