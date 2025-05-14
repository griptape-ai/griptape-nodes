import openai
from griptape.drivers.audio_transcription.openai import OpenAiAudioTranscriptionDriver
from griptape.tools.audio_transcription.tool import AudioTranscriptionTool as GtAudioTranscriptionTool

from griptape_nodes_library.tools.base_tool import BaseTool

API_KEY_ENV_VAR = "OPENAI_API_KEY"
SERVICE = "OpenAI"
DEFAULT_MODEL = "whisper-1"


class AudioTranscription(BaseTool):
    def process(self) -> None:
        self.parameter_values.get("off_prompt", True)
        driver = self.parameter_values.get("driver", None)

        # Set default driver if none provided
        if not driver:
            driver = OpenAiAudioTranscriptionDriver(model=DEFAULT_MODEL)

        # Create the tool with parameters
        tool = GtAudioTranscriptionTool(audio_transcription_driver=driver)

        # Set the output
        self.parameter_output_values["tool"] = tool

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = []
        if self.parameter_values.get("driver", None):
            return exceptions
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
        except openai.AuthenticationError as e:
            exceptions.append(e)
        return exceptions if exceptions else None
