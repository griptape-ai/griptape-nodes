from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.audio_utils import dict_to_audio_url_artifact


class LoadAudio(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Audio"
        self.description = "Load an audio file"
        audio_parameter = Parameter(
            name="audio",
            input_types=["AudioArtifact", "AudioUrlArtifact"],
            type="AudioArtifact",
            output_type="AudioUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True},
            tooltip="The audio that has been generated.",
        )
        self.add_parameter(audio_parameter)

    def process(self) -> None:
        audio = self.get_parameter_value("audio")

        if isinstance(audio, dict):
            audio_artifact = dict_to_audio_url_artifact(audio)
        else:
            audio_artifact = audio

        self.parameter_output_values["audio"] = audio_artifact
