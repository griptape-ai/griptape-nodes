from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.audio_utils import dict_to_audio_url_artifact


class Microphone(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        audio_parameter = Parameter(
            name="audio",
            input_types=["AudioArtifact", "AudioUrlArtifact", "dict"],
            type="AudioArtifact",
            output_type="AudioUrlArtifact",
            ui_options={"microphone_capture_audio": True},
            tooltip="The audio that has been captured.",
            allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(audio_parameter)

    def process(self) -> None:
        audio = self.get_parameter_value("audio")

        if isinstance(audio, dict):
            audio_artifact = dict_to_audio_url_artifact(audio)
        else:
            audio_artifact = audio

        self.parameter_output_values["audio"] = audio_artifact
