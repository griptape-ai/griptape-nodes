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

    def validate_node_before_run(self) -> list[Exception] | None:
        """Validates a node is configured correctly before a run is started. This prevents wasting time executing nodes if there is a known failure.

        Override this method in your Node classes to add custom validation logic to confirm that your Node
        will not encounter any issues before a run is started.

        If there are no errors, return None. Otherwise, collate all errors into a list of Exceptions. These
        Exceptions will be surfaced to the user in order to give them directed feedback for how to resolve
        the issues.

        Returns:
            list[Exception] | None: A list of Exceptions if validation fails, otherwise None.
        """
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
