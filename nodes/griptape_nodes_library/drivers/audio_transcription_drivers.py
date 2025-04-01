import openai
from griptape.drivers.audio_transcription.openai import OpenAiAudioTranscriptionDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.base_driver import BaseDriverNode


class BaseAudioTranscriptionDriverNode(BaseDriverNode):
    """Base driver node for creating Griptape Drivers.

    This node provides a generic implementation for initializing Griptape audio_transcription_drivers with configurable parameters.

    Attributes:
        driver (dict): A dictionary representation of the created tool.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(Parameter(name="model", allowed_types=["str"], default_value=None, tooltip=""))


class OpenAiAudioTranscriptionDriverNode(BaseAudioTranscriptionDriverNode):
    def process(self) -> None:
        model = self.parameter_values.get("model", None)
        if model:
            driver = OpenAiAudioTranscriptionDriver(model=model)
        else:
            driver = OpenAiAudioTranscriptionDriver(model="whisper-1")

        # Set the output
        self.parameter_output_values["driver"] = driver

    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        key = "OPENAI_API_KEY"
        api_key = self.get_config_value("OpenAI", key)
        if not api_key:
            msg = f"{key} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
        except openai.AuthenticationError as e:
            exceptions.append(e)
        return exceptions if exceptions else None
