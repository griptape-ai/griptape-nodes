from typing import Any

from griptape.artifacts import AudioArtifact
from griptape.loaders import AudioLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button

DEFAULT_FILENAME = "griptape_nodes.mp3"


def to_audio_artifact(audio: AudioArtifact | dict) -> AudioArtifact:
    """Convert an audio or a dictionary to an AudioArtifact."""
    if isinstance(audio, dict):
        # Load audio from URL if provided in dictionary
        if "url" in audio:
            return AudioLoader().parse(audio["url"])
        error_msg = "Dictionary must contain 'url' key"
        raise ValueError(error_msg)
    return audio


class SaveAudio(ControlNode):
    """Save an audio file to disk."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add audio input parameter
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["AudioUrlArtifact", "AudioArtifact", "dict"],
                type="AudioArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The audio to save to file",
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
                tooltip="The output filename with extension (.mp3, .wav, etc.). Note that the audio is not transcoded, so the extension should match the original format.",
                traits={Button(button_type="save")},
            )
        )

    def process(self) -> None:
        audio = self.get_parameter_value("audio")

        if not audio:
            logger.info("No audio provided to save")
            return

        output_file = self.get_parameter_value("output_path")

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        try:
            audio_artifact = to_audio_artifact(audio)
            saved_path = GriptapeNodes.StaticFilesManager().save_static_file(audio_artifact.to_bytes(), output_file)

            success_msg = f"Saved audio: {saved_path}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving audio: {error_message}"
            raise ValueError(msg) from e
